from sqlalchemy import select

from app.database.models import AuditEvent
from tests.api.test_customers_cases import add_user, login, two

API = "/api/v1"

FULL = {
    "name": "Alpha Trading", "industry": "Retail", "country": "Ghana", "timezone": "Africa/Accra",
    "description": "We sell phones.", "contact_phone": "+233 24 123 4567", "contact_email": "Hello@Alpha.test",
    "website": "https://alpha.test", "address": "1 High St, Accra",
    "branches": [{"name": "Osu", "address": "Oxford St", "phone": "+233201112222"}],
    "hours": {"mon": [["08:00", "17:00"]]},
    "policies": [{"title": "Refunds", "text": "Within 7 days with receipt."}],
    "languages": ["English", "Twi", "english"],
    "preferences": {"greeting": "Akwaaba!", "tone": "friendly"},
}


async def test_profile_round_trip_and_defaults(env):
    a, _, b, _, _ = await two(env)
    try:
        empty = (await a.get(f"{API}/business/profile")).json()
        assert empty["name"] == "Alpha" and empty["branches"] == [] and empty["hours"] is None and empty["preferences"] == {}
        r = await a.put(f"{API}/business/profile", json=FULL)
        assert r.status_code == 200, r.text
        got = (await a.get(f"{API}/business/profile")).json()
        assert got["contact_email"] == "hello@alpha.test"
        assert got["languages"] == ["English", "Twi"]          # duplicates dropped, case-insensitively
        assert got["branches"][0]["name"] == "Osu" and got["timezone"] == "Africa/Accra"
        assert (await a.get(f"{API}/auth/me")).json()["business"]["name"] == "Alpha Trading"
    finally:
        await a.aclose(); await b.aclose()


async def test_profile_is_isolated_between_businesses(env):
    a, _, b, _, _ = await two(env)
    try:
        assert (await a.put(f"{API}/business/profile", json=FULL)).status_code == 200
        other = (await b.get(f"{API}/business/profile")).json()
        assert other["name"] == "Beta" and other["description"] is None and other["policies"] == [] and other["contact_email"] is None
        assert (await b.get(f"{API}/auth/me")).json()["business"]["name"] == "Beta"
    finally:
        await a.aclose(); await b.aclose()


async def test_profile_write_needs_permission_but_any_member_reads(env):
    a, a_id, b, _, factory = await two(env)
    try:
        await add_user(factory, a_id, "Staff", ["customers:read"], "s@a.test")
        s = await login(env, "s@a.test")
        assert (await s.get(f"{API}/business/profile")).status_code == 200
        assert (await s.put(f"{API}/business/profile", json=FULL)).status_code == 403
        assert (await a.get(f"{API}/business/profile")).json()["description"] is None
        from tests.api.conftest import make_client
        async with make_client(env[0]) as anon:
            assert (await anon.get(f"{API}/business/profile")).status_code == 401
            assert (await anon.put(f"{API}/business/profile", json=FULL)).status_code == 401
        await s.aclose()
    finally:
        await a.aclose(); await b.aclose()


async def test_profile_validation_rejects_bad_input(env):
    a, _, b, b_id, _ = await two(env)
    try:
        bad = [
            {"name": "x"}, {"contact_email": "nope"}, {"contact_phone": "abc"}, {"website": "ftp://x.y"},
            {"timezone": "Mars/Base"}, {"hours": {"mon": [["17:00", "08:00"]]}}, {"hours": {"xyz": []}},
            {"branches": [{"name": " "}]}, {"branches": [{"name": "A", "phone": "bad"}]},
            {"policies": [{"title": "t", "text": " "}]}, {"languages": [""]}, {"languages": ["x"] * 13},
            {"preferences": {"tone": "rude"}}, {"preferences": {"other": "x"}},
            {"business_id": str(b_id)}, {"id": str(b_id)}, {"description": "d" * 2001},
        ]
        for patch in bad:
            r = await a.put(f"{API}/business/profile", json={**FULL, **patch})
            assert r.status_code == 422, patch
        assert (await a.get(f"{API}/business/profile")).json()["name"] == "Alpha"   # nothing half-saved
    finally:
        await a.aclose(); await b.aclose()


async def test_profile_audit_names_fields_only(env):
    a, a_id, b, _, factory = await two(env)
    try:
        await a.put(f"{API}/business/profile", json=FULL)
        async with factory() as db:
            ev = (await db.execute(select(AuditEvent).where(AuditEvent.action == "business.profile_updated"))).scalars().all()
        assert [e.business_id for e in ev] == [a_id]
        assert "contact_email" in ev[0].detail["changed"] and "policies" in ev[0].detail["changed"]
        blob = str(ev[0].detail)
        for secret in ("alpha.test", "Refunds", "233", "Oxford"):
            assert secret not in blob
    finally:
        await a.aclose(); await b.aclose()
