import json
import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.core.security import token_digest
from app.database.models import AuditEvent, AuthSession, EmailVerification, PasswordReset, User
from app.main import create_app
from app.services.email import EmailError, EmailMessage, EmailService, build_email_service
from app.services.email.resend import ResendProvider
from tests.api.conftest import make_client
from tests.api.test_customers_cases import add_user, login, two
from tests.api.test_team import invite

API = "/api/v1"


class FakeProvider:
    name = "fake"

    def __init__(self, fail=False):
        self.sent: list[tuple[str, EmailMessage]] = []
        self.fail = fail

    async def send(self, sender, message):
        if self.fail:
            raise EmailError("boom")
        self.sent.append((sender, message))


async def verified_two(e, fp=None):
    """Two businesses on an email-enabled app, owners already verified, verification mail cleared."""
    a, a_id, b, b_id, factory = await two(e)
    async with factory() as db:
        for u in (await db.execute(select(User))).scalars():
            u.email_verified_at = datetime.now(timezone.utc)
        await db.commit()
    if fp is not None:
        fp.sent.clear()
    return a, a_id, b, b_id, factory


def with_email(env, provider):
    """Rebuild the app on the same database with a fake email provider."""
    _, factory, settings = env
    svc = EmailService(provider, "KASORA <no-reply@mail.test>", "https://app.test")
    return (create_app(settings, factory, email_service=svc), factory, settings)


async def test_invite_email_carries_a_fragment_link_and_reports_sent(env):
    fp = FakeProvider()
    e = with_email(env, fp)
    a, _, b, _, _ = await verified_two(e, fp)
    try:
        r = await invite(a, "kofi@a.test")
        assert r.status_code == 201 and r.json()["email_sent"] is True
        sender, msg = fp.sent[0]
        assert sender == "KASORA <no-reply@mail.test>" and msg.to == "kofi@a.test"
        assert f"https://app.test/accept-invite#token={r.json()['token']}" in msg.text
        assert "Alpha" in msg.subject and "Employee" in msg.text
    finally:
        await a.aclose(); await b.aclose()


@pytest.mark.parametrize("provider", [FakeProvider(fail=True), None])
async def test_email_failure_or_off_never_breaks_the_invite(env, provider):
    e = with_email(env, provider)
    a, _, b, _, _ = await verified_two(e)
    try:
        r = await invite(a, "kofi@a.test")
        assert r.status_code == 201 and r.json()["email_sent"] is False and r.json()["token"]
    finally:
        await a.aclose(); await b.aclose()


async def test_forgot_password_is_identical_for_unknown_and_disabled_accounts(env):
    fp = FakeProvider()
    e = with_email(env, fp)
    a, a_id, b, _, factory = await verified_two(e, fp)
    try:
        await add_user(factory, a_id, "Staff", ["customers:read"], "s@a.test")
        async with factory() as db:
            u = (await db.execute(select(User).where(User.email == "s@a.test"))).scalar_one()
            u.status = "disabled"
            await db.commit()
        async with make_client(e[0]) as anon:
            for email in ("nobody@x.test", "s@a.test"):
                assert (await anon.post(f"{API}/auth/forgot-password", json={"email": email})).status_code == 204
            assert fp.sent == []
            assert (await anon.post(f"{API}/auth/forgot-password", json={"email": "a@a.test"})).status_code == 204
        assert len(fp.sent) == 1 and fp.sent[0][1].to == "a@a.test"
    finally:
        await a.aclose(); await b.aclose()


def _token(msg):
    return msg.text.split("#token=")[1].split()[0]


async def test_reset_flow_single_use_hashed_expiring_and_signs_out_everywhere(env):
    fp = FakeProvider()
    e = with_email(env, fp)
    a, a_id, b, _, factory = await verified_two(e, fp)
    try:
        async with make_client(e[0]) as anon:
            await anon.post(f"{API}/auth/forgot-password", json={"email": "a@a.test"})
            token = _token(fp.sent[0][1])
            async with factory() as db:  # only a hash is stored
                row = (await db.execute(select(PasswordReset))).scalar_one()
                assert row.token_hash == token_digest(token) and token not in row.token_hash
            assert (await a.get(f"{API}/auth/me")).status_code == 200  # signed in before
            assert (await anon.post(f"{API}/auth/reset-password", json={"token": token, "password": "short"})).status_code == 422
            r = await anon.post(f"{API}/auth/reset-password", json={"token": token, "password": "brand-new-passphrase"})
            assert r.status_code == 204
            assert (await a.get(f"{API}/auth/me")).status_code == 401  # old session revoked
            assert (await anon.post(f"{API}/auth/login", json={"email": "a@a.test", "password": "a-long-passphrase"})).status_code == 401
            assert (await anon.post(f"{API}/auth/login", json={"email": "a@a.test", "password": "brand-new-passphrase"})).status_code == 200
            # single use
            assert (await anon.post(f"{API}/auth/reset-password", json={"token": token, "password": "another-new-passphrase"})).status_code == 404
            assert "changed" in fp.sent[1][1].subject  # security notice
        assert (await b.get(f"{API}/auth/me")).status_code == 200  # another business untouched
        async with factory() as db:
            acts = [x.action for x in (await db.execute(select(AuditEvent).order_by(AuditEvent.created_at))).scalars()]
            assert "password.reset_requested" in acts and "password.reset_completed" in acts
    finally:
        await a.aclose(); await b.aclose()


async def test_reset_rejects_unknown_expired_and_replaced_tokens(env):
    fp = FakeProvider()
    e = with_email(env, fp)
    a, _, b, _, factory = await verified_two(e, fp)
    try:
        async with make_client(e[0]) as anon:
            ok = {"password": "brand-new-passphrase"}
            assert (await anon.post(f"{API}/auth/reset-password", json={"token": "x" * 30, **ok})).status_code == 404
            await anon.post(f"{API}/auth/forgot-password", json={"email": "a@a.test"})
            first = _token(fp.sent[0][1])
            await anon.post(f"{API}/auth/forgot-password", json={"email": "a@a.test"})
            second = _token(fp.sent[1][1])
            assert (await anon.post(f"{API}/auth/reset-password", json={"token": first, **ok})).status_code == 404  # replaced
            async with factory() as db:
                row = (await db.execute(select(PasswordReset))).scalar_one()
                row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
                await db.commit()
            assert (await anon.post(f"{API}/auth/reset-password", json={"token": second, **ok})).status_code == 404  # expired
    finally:
        await a.aclose(); await b.aclose()


async def test_resend_request_shape_and_secret_handling(caplog):
    calls = []

    def transport(url, headers, body):
        calls.append((url, headers, json.loads(body)))
        return 200, '{"id":"abc"}'

    p = ResendProvider("re_SECRET123", transport=transport)
    await p.send("KASORA <no-reply@mail.test>", EmailMessage("x@y.test", "Hi", "plain", "<p>html</p>", idempotency_key="k1"))
    url, headers, body = calls[0]
    assert url == "https://api.resend.com/emails" and headers["Authorization"] == "Bearer re_SECRET123"
    assert headers["Idempotency-Key"] == "k1"
    assert body == {"from": "KASORA <no-reply@mail.test>", "to": ["x@y.test"], "subject": "Hi", "html": "<p>html</p>", "text": "plain"}

    def rejecting(url, headers, body):
        return 403, '{"message":"domain not verified re_SECRET123 secret body"}'

    def exploding(url, headers, body):
        raise OSError("re_SECRET123 in a network error")

    for t in (rejecting, exploding):
        with pytest.raises(EmailError) as err:
            await ResendProvider("re_SECRET123", transport=t).send("a@b.test", EmailMessage("x@y.test", "Hi", "t", "h"))
        assert "re_SECRET123" not in str(err.value) and "secret body" not in str(err.value)

    caplog.set_level(logging.INFO, logger="app.email")
    svc = EmailService(ResendProvider("re_SECRET123", transport=rejecting), "a@b.test", "https://app.test")
    assert await svc.send_password_reset("victim@x.test", "TOKEN" * 8, 60) is False
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "re_SECRET123" not in logged and "victim@x.test" not in logged and "TOKEN" not in logged


def test_service_is_off_unless_fully_configured():
    base = dict(_env_file=None, environment="test")
    assert not build_email_service(Settings(**base)).enabled
    assert not build_email_service(Settings(**base, email_provider="resend")).enabled  # no key, no sender
    assert not build_email_service(Settings(**base, email_provider="resend", resend_api_key="k", email_domain_verified=True)).enabled  # no sender
    full = dict(email_provider="resend", resend_api_key="k", email_from="a@b.test")
    assert not build_email_service(Settings(**base, **full)).enabled  # domain not confirmed verified: still off
    assert build_email_service(Settings(**base, **full, email_domain_verified=True)).enabled


def test_html_escapes_the_business_name():
    from app.services.email.service import EmailService as S
    text, html = S(None, None, "https://x")._wrap("Hi <b>", ["<script>alert(1)</script>"], ("Go", "https://x/?a=1&b=2"), "f")
    assert "<script>" not in html and "&lt;script&gt;" in html and "&amp;b=2" in html


async def test_registration_sends_a_verification_link_and_it_verifies_once(env):
    fp = FakeProvider()
    e = with_email(env, fp)
    a, a_id, b, _, factory = await two(e)
    try:
        assert len(fp.sent) == 2 and {m.to for _, m in fp.sent} == {"a@a.test", "b@b.test"}
        me = (await a.get(f"{API}/auth/me")).json()["user"]
        assert me["email_verified"] is False and me["email_verification_required"] is True
        msg = next(m for _, m in fp.sent if m.to == "a@a.test")
        token = msg.text.split("#token=")[1].split()[0]
        assert "https://app.test/verify-email#token=" in msg.text
        async with factory() as db:  # only a hash is stored
            row = (await db.execute(select(EmailVerification).where(EmailVerification.token_hash == token_digest(token)))).scalar_one()
            assert token not in row.token_hash
        # an unverified owner cannot invite yet
        assert (await invite(a, "kofi@a.test")).status_code == 403
        async with make_client(e[0]) as anon:
            assert (await anon.post(f"{API}/auth/verify-email", json={"token": "x" * 30})).status_code == 404
            assert (await anon.post(f"{API}/auth/verify-email", json={"token": token})).status_code == 204
            assert (await anon.post(f"{API}/auth/verify-email", json={"token": token})).status_code == 404  # single use
        me = (await a.get(f"{API}/auth/me")).json()["user"]
        assert me["email_verified"] is True and me["email_verification_required"] is False
        assert (await b.get(f"{API}/auth/me")).json()["user"]["email_verified"] is False  # the other owner is untouched
        assert (await invite(a, "kofi@a.test")).status_code == 201
    finally:
        await a.aclose(); await b.aclose()


async def test_verification_expires_resend_replaces_and_invited_staff_start_verified(env):
    fp = FakeProvider()
    e = with_email(env, fp)
    a, a_id, b, _, factory = await two(e)
    try:
        first = next(m for _, m in fp.sent if m.to == "a@a.test").text.split("#token=")[1].split()[0]
        fp.sent.clear()
        assert (await a.post(f"{API}/auth/resend-verification")).status_code == 204
        second = fp.sent[0][1].text.split("#token=")[1].split()[0]
        async with make_client(e[0]) as anon:
            assert (await anon.post(f"{API}/auth/verify-email", json={"token": first})).status_code == 404  # replaced
            async with factory() as db:
                row = (await db.execute(select(EmailVerification).where(EmailVerification.token_hash == token_digest(second)))).scalar_one()
                row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
                await db.commit()
            assert (await anon.post(f"{API}/auth/verify-email", json={"token": second})).status_code == 404  # expired
        # invited staff are verified because the invitation reached their address
        async with factory() as db:
            for u in (await db.execute(select(User))).scalars():
                u.email_verified_at = datetime.now(timezone.utc)
            await db.commit()
        tok = (await invite(a, "kofi@a.test")).json()["token"]
        from tests.api.test_team import accept
        c, r = await accept(e, tok, full_name="Kofi Boateng")
        assert r.status_code == 201 and r.json()["user"]["email_verified"] is True
        await c.aclose()
    finally:
        await a.aclose(); await b.aclose()


async def test_resend_needs_email_on_and_a_signed_in_user(env):
    off = with_email(env, None)
    a, _, b, _, _ = await two(off)
    try:
        r = await a.post(f"{API}/auth/resend-verification")
        assert r.status_code == 503 and "not set up" in r.json()["detail"]
        me = (await a.get(f"{API}/auth/me")).json()["user"]
        assert me["email_verification_required"] is False  # no banner while email is off
        assert (await invite(a, "kofi@a.test")).status_code == 201  # and nothing is blocked
        async with make_client(off[0]) as anon:
            assert (await anon.post(f"{API}/auth/resend-verification")).status_code == 401
    finally:
        await a.aclose(); await b.aclose()
