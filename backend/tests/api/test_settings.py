from sqlalchemy import select

from app.database.models import AuditEvent
from tests.api.test_customers_cases import add_user, login, two

API = "/api/v1"


async def test_profile_rename_self_only(env):
    a, a_id, b, b_id, factory = await two(env)
    try:
        await add_user(factory, a_id, "Staff", ["customers:read"], "e@a.test")
        e = await login(env, "e@a.test")
        r = await e.patch(f"{API}/profile", json={"full_name": "  Efua Owusu "})
        assert r.status_code == 200, r.text
        assert r.json()["user"]["full_name"] == "Efua Owusu"
        assert (await e.get(f"{API}/auth/me")).json()["user"]["full_name"] == "Efua Owusu"
        for c in (a, b):  # nobody else's name moved
            assert (await c.get(f"{API}/auth/me")).json()["user"]["full_name"] != "Efua Owusu"
        await e.aclose()
    finally:
        await a.aclose(); await b.aclose()


async def test_profile_validation_and_auth(env):
    a, _, b, _, _ = await two(env)
    try:
        for bad in ({"full_name": ""}, {"full_name": " a "}, {"full_name": "x" * 121}, {"full_name": "Ama", "id": "1"},
                    {"full_name": "Ama", "email": "x@y.z"}, {}):
            assert (await a.patch(f"{API}/profile", json=bad)).status_code == 422, bad
        from tests.api.conftest import make_client
        async with make_client(env[0]) as anon:
            assert (await anon.patch(f"{API}/profile", json={"full_name": "Ama"})).status_code == 401
    finally:
        await a.aclose(); await b.aclose()


async def test_business_rename_isolated_audited_and_guarded(env):
    a, a_id, b, b_id, factory = await two(env)
    try:
        await add_user(factory, a_id, "Limited", ["customers:write"], "m@a.test")
        m = await login(env, "m@a.test")
        r = await m.patch(f"{API}/business", json={"name": "Hacked Co"})
        assert r.status_code == 403
        assert (await a.get(f"{API}/auth/me")).json()["business"]["name"] == "Alpha"

        r = await a.patch(f"{API}/business", json={"name": "  Alpha Trading "})
        assert r.status_code == 200, r.text
        assert r.json()["business"]["name"] == "Alpha Trading"
        assert (await a.get(f"{API}/auth/me")).json()["business"]["name"] == "Alpha Trading"
        assert (await b.get(f"{API}/auth/me")).json()["business"]["name"] == "Beta"

        for bad in ({"name": "x"}, {"name": "n" * 121}, {"name": "Okay", "business_id": str(b_id)}, {"name": "Okay", "id": str(b_id)}):
            assert (await a.patch(f"{API}/business", json=bad)).status_code == 422, bad
        assert (await b.get(f"{API}/auth/me")).json()["business"]["name"] == "Beta"

        async with factory() as db:
            ev = (await db.execute(select(AuditEvent).where(AuditEvent.action == "business.updated"))).scalars().all()
        assert [e.business_id for e in ev] == [a_id]
        assert ev[0].detail == {"changed": ["name"]}
        from tests.api.conftest import make_client
        async with make_client(env[0]) as anon:
            assert (await anon.patch(f"{API}/business", json={"name": "Nope"})).status_code == 401
        await m.aclose()
    finally:
        await a.aclose(); await b.aclose()
