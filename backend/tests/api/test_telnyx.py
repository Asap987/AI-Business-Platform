"""Telnyx adapter: no network, no account. Fake HTTP, locally generated Ed25519 keys, and the real routing service."""

import asyncio
import base64
import json
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.config import Settings
from app.database.models import Department, Employee
from app.main import create_app
from app.services.telephony import TransferService
from app.services.telephony.factory import build_telephony, missing_for_live_telephony
from app.services.telephony.interfaces import TransferOutcome as O, TransferTarget
from app.services.telephony.mock import MockTelephony
from app.services.telephony.telnyx import TelnyxEventRegistry, TelnyxTelephony, _marker, verify_signature
from tests.api.conftest import make_client
from tests.api.test_customers_cases import two

KEY = Ed25519PrivateKey.generate()
PUB = base64.b64encode(KEY.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
SECRET = "sk-test-do-not-log-me"
TARGET = TransferTarget("+233200000001", "Accounts")


def sign(body: bytes, ts: int | None = None, key=KEY) -> dict[str, str]:
    ts = str(ts if ts is not None else int(time.time()))
    return {"telnyx-timestamp": ts, "telnyx-signature-ed25519": base64.b64encode(key.sign(ts.encode() + b"|" + body)).decode()}


def event(kind, attempt, eid, **payload):
    return {"data": {"id": eid, "event_type": kind, "payload": {"client_state": _marker(attempt), **payload}}}


class FakeHttp:
    """Records requests. ``on_post(attempt_id, registry)`` lets a test deliver webhooks as Telnyx would, after the command."""

    def __init__(self, registry, status=200, raises=None, then=None):
        self.registry, self.status, self.raises, self.then, self.calls = registry, status, raises, then, []

    async def __call__(self, url, headers, body, timeout):
        self.calls.append((url, headers, body))
        if self.raises:
            raise self.raises
        if self.then and self.status == 200:
            asyncio.get_running_loop().call_later(0.01, self.then, body["command_id"], self.registry)
        return self.status, {"data": {"result": "ok"}}


def adapter(http, registry, **kw):
    return TelnyxTelephony(SECRET, registry, http, timeout_secs=kw.pop("timeout_secs", 5), wait_margin_secs=kw.pop("wait_margin_secs", 0.2), **kw)


# ---------------------------------------------------------------- signatures
def test_signature_accepts_only_the_exact_signed_message():
    body = b'{"data":{}}'
    h = sign(body)
    assert verify_signature(PUB, h["telnyx-timestamp"], h["telnyx-signature-ed25519"], body)
    assert not verify_signature(PUB, h["telnyx-timestamp"], h["telnyx-signature-ed25519"], body + b" ")          # body changed
    assert not verify_signature(PUB, str(int(h["telnyx-timestamp"]) + 1), h["telnyx-signature-ed25519"], body)   # timestamp changed
    other = sign(body, key=Ed25519PrivateKey.generate())
    assert not verify_signature(PUB, other["telnyx-timestamp"], other["telnyx-signature-ed25519"], body)         # someone else's key
    old = sign(body, ts=int(time.time()) - 301)
    assert not verify_signature(PUB, old["telnyx-timestamp"], old["telnyx-signature-ed25519"], body)             # replay
    for bad in (None, "", "x", "!!!"):
        assert not verify_signature(PUB, h["telnyx-timestamp"], bad, body)
        assert not verify_signature(bad or "", h["telnyx-timestamp"], h["telnyx-signature-ed25519"], body)
    assert not verify_signature(PUB, "not-a-number", h["telnyx-signature-ed25519"], body)


# ---------------------------------------------------------------- adapter
async def test_bridged_event_confirms_and_the_command_is_what_telnyx_documents():
    reg = TelnyxEventRegistry()
    http = FakeHttp(reg, then=lambda a, r: r.handle_event(event("call.bridged", a, "e1")))
    res = await adapter(http, reg, from_number="+233300000000").transfer_call("v3:abc", TransferTarget("+233200000001", "Accounts", "12#"))
    assert res.outcome is O.CONFIRMED
    url, headers, body = http.calls[0]
    assert url == "https://api.telnyx.com/v2/calls/v3:abc/actions/transfer" and headers == {"Authorization": f"Bearer {SECRET}"}
    assert body["to"] == "+233200000001" and body["from"] == "+233300000000" and body["timeout_secs"] == 5
    assert body["send_digits_on_answer"] == "ww12#" and body["command_id"] and body["target_leg_client_state"] == body["client_state"]
    assert SECRET not in json.dumps(body)


async def test_hangup_causes_map_to_outcomes():
    for cause, want in (("timeout", O.NO_ANSWER), ("user_busy", O.BUSY), ("call_rejected", O.FAILED), (None, O.FAILED)):
        reg = TelnyxEventRegistry()
        res = await adapter(FakeHttp(reg, then=lambda a, r, c=cause: r.handle_event(event("call.hangup", a, "h", hangup_cause=c))), reg).transfer_call("c", TARGET)
        assert res.outcome is want, cause


async def test_no_final_event_is_unconfirmed_never_success():
    reg = TelnyxEventRegistry()
    res = await adapter(FakeHttp(reg), reg, timeout_secs=5, wait_margin_secs=-4.9).transfer_call("c", TARGET)   # waits 0.1 s
    assert res.outcome is O.UNCONFIRMED
    answered_only = FakeHttp(reg, then=lambda a, r: r.handle_event(event("call.answered", a, "a1")))             # answered is not bridged
    assert (await adapter(answered_only, reg, wait_margin_secs=-4.9).transfer_call("c", TARGET)).outcome is O.UNCONFIRMED


async def test_http_problems_are_classified_and_nothing_is_confirmed():
    reg = TelnyxEventRegistry()
    assert (await adapter(FakeHttp(reg, status=422), reg).transfer_call("c", TARGET)).outcome is O.FAILED          # rejected: call ended, bad number...
    assert (await adapter(FakeHttp(reg, status=503), reg).transfer_call("c", TARGET)).outcome is O.UNCONFIRMED     # may have been accepted
    assert (await adapter(FakeHttp(reg, raises=OSError("down")), reg).transfer_call("c", TARGET)).outcome is O.UNCONFIRMED


async def test_invalid_numbers_are_refused_without_contacting_telnyx():
    reg = TelnyxEventRegistry()
    http = FakeHttp(reg)
    for target in (TransferTarget("0200000001", "x"), TransferTarget("+233 200", "x"), TransferTarget("", "x"), TransferTarget("+233200000001", "x", "1;rm")):
        assert (await adapter(http, reg).transfer_call("c", target)).outcome is O.FAILED
    assert (await adapter(http, reg).transfer_call("", TARGET)).outcome is O.FAILED
    assert http.calls == []


async def test_other_events_cannot_settle_an_attempt():
    reg = TelnyxEventRegistry()
    seen = []

    def inject(attempt, r):
        seen.append(r.handle_event({"data": {"id": "z1", "event_type": "call.bridged", "payload": {"client_state": base64.b64encode(b"someone-else").decode()}}}))
        seen.append(r.handle_event({"data": {"id": "z2", "event_type": "call.bridged", "payload": {}}}))
        seen.append(r.handle_event({"nonsense": 1}))
        seen.append(r.handle_event(event("call.bridged", "a-different-attempt", "z3")))
        seen.append(r.handle_event(event("call.hangup", attempt, "z4", hangup_cause="timeout")))
        seen.append(r.handle_event(event("call.bridged", attempt, "z5")))        # late: already settled

    res = await adapter(FakeHttp(reg, then=inject), reg).transfer_call("c", TARGET)
    assert seen == [False, False, False, False, True, False] and res.outcome is O.NO_ANSWER


async def test_duplicate_event_ids_are_ignored():
    reg = TelnyxEventRegistry()
    seen = []

    def inject(attempt, r):
        seen.append(r.handle_event(event("call.hangup", "other", "dup", hangup_cause="timeout")))
        seen.append(r.handle_event(event("call.bridged", attempt, "dup")))       # same id as one already seen
        seen.append(r.handle_event(event("call.bridged", attempt, "fresh")))

    res = await adapter(FakeHttp(reg, then=inject), reg).transfer_call("c", TARGET)
    assert seen == [False, False, True] and res.outcome is O.CONFIRMED


async def test_the_key_never_reaches_the_log(caplog):
    import logging
    reg = TelnyxEventRegistry()
    with caplog.at_level(logging.DEBUG):
        await adapter(FakeHttp(reg, status=422), reg).transfer_call("c", TARGET)
        await adapter(FakeHttp(reg, raises=OSError(SECRET)), reg).transfer_call("c", TARGET)
    assert SECRET not in caplog.text and "233200000001" not in caplog.text


# ---------------------------------------------------------------- with the real routing service
async def test_routing_reports_a_real_transfer_only_after_the_bridged_event(env):
    a, a_id, b, b_id, factory = await two(env)
    await a.aclose(); await b.aclose()
    async with factory() as db:
        d = Department(business_id=a_id, name="Accounts")
        db.add(d); await db.flush()
        db.add(Employee(business_id=a_id, department_id=d.id, full_name="One", phone="+233200000001"))
        await db.commit()
        dept_id = d.id
    for event_kind, want_decision, simulated in (("call.bridged", "transferred", False), ("call.hangup", "all_attempts_failed", False)):
        reg = TelnyxEventRegistry()
        http = FakeHttp(reg, then=lambda a_, r, k=event_kind: r.handle_event(event(k, a_, "e-" + k, hangup_cause="timeout")))
        async with factory() as db:
            dec = await TransferService(adapter(http, reg)).transfer_to_department(db, a_id, dept_id, "call-1", "t")
        assert dec.decision.value == want_decision and dec.simulated is simulated


# ---------------------------------------------------------------- factory and switches
def live(**kw):
    base = dict(_env_file=None, telephony_provider="telnyx", telephony_live_approved=True, telnyx_api_key=SECRET, telnyx_public_key=PUB)
    return Settings(**{**base, **kw})


def test_the_simulator_is_the_default_and_real_telephony_needs_every_switch():
    assert isinstance(build_telephony(Settings(_env_file=None)), MockTelephony)
    assert isinstance(build_telephony(live(telephony_live_approved=False)), MockTelephony)     # key present but not approved
    assert isinstance(build_telephony(live(telnyx_api_key=None)), MockTelephony)
    assert isinstance(build_telephony(live(telnyx_public_key=None)), MockTelephony)
    assert isinstance(build_telephony(live(telephony_provider="mock")), MockTelephony)
    assert missing_for_live_telephony(Settings(_env_file=None, telnyx_api_key=SECRET)) == ["TELEPHONY_PROVIDER=telnyx"]
    assert missing_for_live_telephony(live(telephony_live_approved=False, telnyx_api_key=None)) == ["TELEPHONY_LIVE_APPROVED", "TELNYX_API_KEY"]
    assert missing_for_live_telephony(live()) == []
    assert build_telephony(live()).name == "telnyx" and build_telephony(live()).simulated is False


def test_settings_do_not_print_the_api_key():
    assert SECRET not in repr(live()) and SECRET not in str(live().model_dump())


# ---------------------------------------------------------------- webhook endpoint
async def test_webhook_is_off_unless_live_telephony_is_configured(env):
    app, factory, _ = env
    async with make_client(app) as c:
        body = b"{}"
        assert (await c.post("/api/v1/telephony/telnyx/webhook", content=body, headers=sign(body))).status_code == 404


async def test_webhook_checks_signature_size_and_settles_a_waiting_attempt(env):
    _, factory, _ = env
    app = create_app(live(), factory)
    from app.services.telephony.telnyx import get_registry
    reg = get_registry()
    waiter = reg.expect("attempt-xyz")
    try:
        async with make_client(app) as c:
            body = json.dumps(event("call.bridged", "attempt-xyz", "evt-1")).encode()
            url = "/api/v1/telephony/telnyx/webhook"
            assert (await c.post(url, content=body)).status_code == 400                                              # unsigned
            assert (await c.post(url, content=body, headers={**sign(body), "telnyx-signature-ed25519": "AAAA"})).status_code == 400
            assert (await c.post(url, content=body, headers=sign(body, key=Ed25519PrivateKey.generate()))).status_code == 400
            assert (await c.post(url, content=body, headers=sign(body, ts=int(time.time()) - 600))).status_code == 400   # replayed
            assert not waiter.done()                                                                                  # nothing settled by bad requests
            big = b"x" * 70000
            assert (await c.post(url, content=big, headers=sign(big))).status_code == 413
            junk = b"not json"
            assert (await c.post(url, content=junk, headers=sign(junk))).status_code == 400
            ok = await c.post(url, content=body, headers=sign(body))
            assert ok.status_code == 200 and ok.json() == {"received": True}
        assert waiter.done() and waiter.result() is O.CONFIRMED
    finally:
        reg.forget("attempt-xyz")
