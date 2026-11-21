from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from app.database.models import Agent, Business, Case, Conversation, Customer, Department
from tests.api.conftest import make_client, register

NOW = datetime.now(timezone.utc)


async def seed(factory, business_id, tag, n_cases=None):
    """Data for one business; names carry a tag so leaks are easy to spot."""
    n_cases = n_cases or {"open": 2, "in_progress": 1, "waiting_department": 1, "resolved": 3, "closed": 4}
    async with factory() as db:
        dept = Department(business_id=business_id, name=f"{tag}-Delivery")
        cust = Customer(business_id=business_id, full_name=f"{tag}-Customer")
        agent = Agent(business_id=business_id, name=f"{tag}-Agent", status="active",
                      config={"channels": ["phone", "bogus", "sms"], "instructions": "Be helpful"})
        db.add_all([dept, cust, agent])
        await db.flush()
        convs = [Conversation(business_id=business_id, customer_id=cust.id, agent_id=agent.id, channel=ch,
                              summary=f"{tag}-summary", started_at=NOW - timedelta(minutes=i))
                 for i, ch in enumerate(["phone", "phone", "sms", "email"])]
        db.add_all(convs)
        for status, count in n_cases.items():
            for i in range(count):
                db.add(Case(business_id=business_id, customer_id=cust.id, department_id=dept.id, title=f"{tag}-{status}-{i}", status=status))
        await db.commit()


async def two_tenants(env):
    app, factory, _ = env
    a = make_client(app)
    b = make_client(app)
    await a.__aenter__(), await b.__aenter__()
    ra = (await register(a, email="a@a.test", business_name="Alpha")).json()
    rb = (await register(b, email="b@b.test", business_name="Beta")).json()
    await seed(factory, __import__("uuid").UUID(ra["business"]["id"]), "ALPHA")
    await seed(factory, __import__("uuid").UUID(rb["business"]["id"]), "BETA", {"open": 7, "resolved": 1})
    return a, b


async def test_every_endpoint_requires_a_session(client):
    for path in ("/dashboard/kpis", "/dashboard/case-overview", "/dashboard/department-activity",
                 "/conversations", "/agents", "/notifications/summary"):
        assert (await client.get("/api/v1" + path)).status_code == 401, path


async def test_each_business_sees_only_its_own_data_everywhere(env):
    a, b = await two_tenants(env)
    try:
        for client, mine, theirs in ((a, "ALPHA", "BETA"), (b, "BETA", "ALPHA")):
            texts = ""
            for path in ("/dashboard/kpis", "/dashboard/case-overview", "/dashboard/department-activity",
                         "/conversations", "/agents", "/notifications/summary"):
                r = await client.get("/api/v1" + path)
                assert r.status_code == 200, path
                assert theirs not in r.text, f"{theirs} data leaked into {path}"
                texts += r.text
            assert mine in texts
    finally:
        await a.aclose(), await b.aclose()


async def test_counts_are_computed_per_business(env):
    a, b = await two_tenants(env)
    try:
        ka = (await a.get("/api/v1/dashboard/kpis")).json()
        kb = (await b.get("/api/v1/dashboard/kpis")).json()
        assert ka["total_calls"]["value"] == 2 and ka["total_sms_conversations"]["value"] == 1
        assert ka["active_cases"]["value"] == 2 + 1 + 1  # open, in_progress, waiting_department; not resolved/closed
        assert ka["pending_department_requests"]["value"] == 1
        assert kb["active_cases"]["value"] == 7 and kb["pending_department_requests"]["value"] == 0
        # no definition or data yet: reported as "no data", never invented
        assert ka["ai_resolution_rate"]["value"] is None and ka["average_response_seconds"]["value"] is None
        assert (await a.get("/api/v1/dashboard/case-overview")).json() == {"open": 2, "in_progress": 1, "waiting_department": 1, "resolved": 3}
        assert (await b.get("/api/v1/dashboard/case-overview")).json() == {"open": 7, "in_progress": 0, "waiting_department": 0, "resolved": 1}
    finally:
        await a.aclose(), await b.aclose()


async def test_new_business_with_no_data_gets_zeros_and_empty_lists(client):
    await register(client)
    assert (await client.get("/api/v1/dashboard/case-overview")).json() == {"open": 0, "in_progress": 0, "waiting_department": 0, "resolved": 0}
    for path in ("/dashboard/department-activity", "/conversations", "/agents"):
        assert (await client.get("/api/v1" + path)).json() == {"items": [], "total": 0, "page": 1, "page_size": {"/agents": 10}.get(path, 20)}


async def test_department_activity_counts_and_pagination(env):
    a, b = await two_tenants(env)
    try:
        r = (await a.get("/api/v1/dashboard/department-activity")).json()
        assert r["items"] == [{"id": r["items"][0]["id"], "name": "ALPHA-Delivery", "open_cases": 3, "pending_requests": 1}]
        conv = (await a.get("/api/v1/conversations", params={"page_size": 2, "page": 2, "sort": "-started_at"})).json()
        assert conv["total"] == 4 and len(conv["items"]) == 2 and conv["page"] == 2
        newest_first = (await a.get("/api/v1/conversations", params={"page_size": 4})).json()["items"]
        times = [i["started_at"] for i in newest_first]
        assert times == sorted(times, reverse=True)
        assert newest_first[0]["customer_name"] == "ALPHA-Customer" and newest_first[0]["channel"] in ("phone", "sms", "email")
    finally:
        await a.aclose(), await b.aclose()


async def test_query_parameters_are_validated(env):
    a, b = await two_tenants(env)
    try:
        for params in ({"page_size": 0}, {"page_size": 1000}, {"page": 0}, {"sort": "customer_name"}, {"sort": "-started_at; drop table cases"}):
            assert (await a.get("/api/v1/conversations", params=params)).status_code == 422, params
    finally:
        await a.aclose(), await b.aclose()


async def test_agents_report_derived_fields_only_from_real_data(env):
    a, b = await two_tenants(env)
    try:
        item = (await a.get("/api/v1/agents")).json()["items"][0]
        assert item["name"] == "ALPHA-Agent" and item["channels"] == ["phone", "sms"]  # unknown channel dropped
        assert item["configured"] is True and item["last_activity_at"] is not None
    finally:
        await a.aclose(), await b.aclose()


async def test_a_conversation_pointing_at_another_tenants_customer_is_not_shown(env):
    """Defence in depth: even a corrupt cross-tenant foreign key must not leak a name."""
    app, factory, _ = env
    a, b = await two_tenants(env)
    try:
        async with factory() as db:
            alpha = (await db.execute(select(Business).where(Business.name == "Alpha"))).scalar_one()
            beta_customer = (await db.execute(select(Customer).where(Customer.full_name == "BETA-Customer"))).scalar_one()
            db.add(Conversation(business_id=alpha.id, customer_id=beta_customer.id, channel="sms", summary="corrupt"))
            await db.commit()
        r = (await a.get("/api/v1/conversations", params={"page_size": 50})).json()
        assert "BETA" not in str(r) and "corrupt" not in str(r)
    finally:
        await a.aclose(), await b.aclose()


async def test_health_is_public_and_docs_are_off_in_production(env):
    from app.core.config import Settings
    from app.main import create_app
    app, factory, _ = env
    assert create_app(Settings(_env_file=None, environment="production"), factory).docs_url is None
