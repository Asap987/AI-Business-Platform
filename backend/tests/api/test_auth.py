from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database.models import AuthSession, Business, Role, User
from app.core.security import token_digest
from tests.api.conftest import ORIGIN, REG, make_client, register


async def test_register_creates_business_roles_admin_and_httponly_cookie(env, client):
    app, factory, settings = env
    r = await register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["email"] == "ama@acme.test" and body["user"]["role"]["name"] == "Administrator"
    assert body["user"]["role"]["permissions"] == ["*"]  # lets the UI hide actions; the API still enforces them
    assert body["business"]["slug"] == "acme-logistics"
    assert "password" not in r.text and "hash" not in r.text
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "secure" not in cookie  # secure only in production
    async with factory() as db:
        roles = (await db.execute(select(Role.name))).scalars().all()
        user = (await db.execute(select(User))).scalar_one()
        token = client.cookies.get("session")
        stored = (await db.execute(select(AuthSession))).scalar_one()
    assert set(roles) == {"Administrator", "Manager", "Employee"}
    assert user.password_hash.startswith("$argon2") and "a-long-passphrase" not in user.password_hash
    assert stored.token_hash == token_digest(token) and stored.token_hash != token  # the token itself is never stored


async def test_secure_flag_is_set_in_production(env):
    app, factory, settings = env
    from app.core.config import Settings
    from app.main import create_app
    prod = create_app(Settings(_env_file=None, environment="production"), factory)
    async with make_client(prod) as c:
        assert "secure" in (await register(c)).headers["set-cookie"].lower()


async def test_duplicate_email_is_rejected_case_insensitively_and_slugs_stay_unique(client):
    assert (await register(client)).status_code == 201
    assert (await register(client, email="AMA@ACME.TEST", business_name="Other")).status_code == 409
    second = await register(client, email="kofi@acme.test")  # same business name
    assert second.json()["business"]["slug"] == "acme-logistics-2"


async def test_validation_errors_use_fastapi_shape_with_field_locations(client):
    r = await register(client, email="not-an-email", password="short")
    assert r.status_code == 422
    fields = {e["loc"][-1] for e in r.json()["detail"]}
    assert {"email", "password"} <= fields


async def test_login_success_sets_a_fresh_session(client):
    await register(client)
    first = client.cookies.get("session")
    client.cookies.clear()
    r = await client.post("/api/v1/auth/login", json={"email": "Ama@Acme.test", "password": REG["password"]})
    assert r.status_code == 200 and r.json()["user"]["full_name"] == "Ama Mensah"
    assert client.cookies.get("session") not in (None, first)


async def test_every_login_failure_looks_the_same(env, client):
    app, factory, _ = env
    await register(client)
    async with factory() as db:
        (await db.execute(select(User))).scalar_one().status = "disabled"
        await db.commit()
    client.cookies.clear()
    wrong_pw = await client.post("/api/v1/auth/login", json={"email": "ama@acme.test", "password": "wrong-wrong-wrong"})
    disabled = await client.post("/api/v1/auth/login", json={"email": "ama@acme.test", "password": REG["password"]})
    unknown = await client.post("/api/v1/auth/login", json={"email": "nobody@acme.test", "password": "whatever-it-is"})
    assert {r.status_code for r in (wrong_pw, disabled, unknown)} == {401}
    assert wrong_pw.json() == disabled.json() == unknown.json()
    assert "session" not in client.cookies


async def test_suspended_business_cannot_log_in_or_use_an_existing_session(env, client):
    app, factory, _ = env
    await register(client)
    async with factory() as db:
        (await db.execute(select(Business))).scalar_one().status = "suspended"
        await db.commit()
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    other = make_client(app)
    async with other:
        r = await other.post("/api/v1/auth/login", json={"email": "ama@acme.test", "password": REG["password"]})
    assert r.status_code == 401


async def test_me_needs_a_session_and_logout_ends_it_server_side(env, client):
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    await register(client)
    token = client.cookies.get("session")
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    out = await client.post("/api/v1/auth/logout")
    assert out.status_code == 204
    # replaying the old cookie must fail: the session row is gone, not just the browser cookie
    replay = make_client(env[0])
    async with replay:
        replay.cookies.set("session", token)
        assert (await replay.get("/api/v1/auth/me")).status_code == 401


async def test_expired_session_is_refused(env, client):
    app, factory, _ = env
    await register(client)
    async with factory() as db:
        (await db.execute(select(AuthSession))).scalar_one().expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_forged_or_garbage_cookie_is_refused(client):
    client.cookies.set("session", "x" * 43)
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_state_changing_requests_need_an_allowed_origin(env):
    app, *_ = env
    for origin in (None, "https://evil.example"):
        async with make_client(app, origin=origin) as c:
            r = await register(c)
            assert r.status_code == 403, origin
    async with make_client(app) as c:
        assert (await register(c)).status_code == 201
        # reads need no Origin
    async with make_client(app, origin=None) as c:
        assert (await c.get("/health")).status_code == 200


async def test_cors_allows_credentials_only_for_the_configured_origin(client):
    ok = await client.options("/api/v1/auth/me", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET"})
    assert ok.headers["access-control-allow-origin"] == ORIGIN and ok.headers["access-control-allow-credentials"] == "true"
    bad = await client.options("/api/v1/auth/me", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers


async def test_login_is_rate_limited(client):
    codes = [
        (await client.post("/api/v1/auth/login", json={"email": "x@y.test", "password": "nope-nope-nope"})).status_code
        for _ in range(7)
    ]
    assert codes[:5] == [401] * 5 and codes[5:] == [429, 429]


async def test_forgot_password_never_reveals_whether_an_account_exists(client):
    await register(client)
    known = await client.post("/api/v1/auth/forgot-password", json={"email": "ama@acme.test"})
    unknown = await client.post("/api/v1/auth/forgot-password", json={"email": "ghost@acme.test"})
    assert known.status_code == unknown.status_code == 204 and known.content == unknown.content


async def test_business_header_must_match_the_session_business(client):
    me = (await register(client)).json()
    own = await client.get("/api/v1/auth/me", headers={"X-Business-Id": me["business"]["id"]})
    other = await client.get("/api/v1/auth/me", headers={"X-Business-Id": "00000000-0000-0000-0000-000000000001"})
    assert own.status_code == 200 and other.status_code == 403
