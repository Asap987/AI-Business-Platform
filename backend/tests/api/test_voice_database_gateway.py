from uuid import UUID, uuid4

from sqlalchemy import select

from app.database.models import Case, CaseEvent, Customer, Department
from app.services.voice.database_gateway import DatabaseBusinessGateway
from tests.api.conftest import make_client, register


async def setup(env):
    app, factory, _ = env
    async with make_client(app) as a, make_client(app) as b:
        ra = (await register(a, business_name="Alpha", email="a@a.test")).json()
        rb = (await register(b, business_name="Beta", email="b@b.test")).json()
    a_id, b_id = UUID(ra["business"]["id"]), UUID(rb["business"]["id"])
    async with factory() as db:
        ca, cb = Customer(business_id=a_id, full_name="Alpha Cust"), Customer(business_id=b_id, full_name="Beta Cust")
        db.add_all([ca, cb, Department(business_id=a_id, name="Delivery"), Department(business_id=b_id, name="Sales")])
        await db.commit()
    return factory, a_id, b_id, ca.id, cb.id


def gateway(factory, customer_id):
    async def resolver(business_id, session_id):
        return customer_id
    return DatabaseBusinessGateway(factory, resolver)


async def run(gw, biz, tool, args):
    return await gw.execute(business_id=biz, session_id=uuid4(), tool_name=tool, arguments=args)


async def test_create_case_is_stored_for_the_right_business_and_attributed_to_the_ai(env):
    factory, a_id, b_id, ca, cb = await setup(env)
    res = await run(gateway(factory, ca), a_id, "create_case", {"title": "Late parcel", "department": "delivery"})
    assert res.ok and "Case created for delivery" in res.summary
    async with factory() as db:
        case = (await db.execute(select(Case))).scalar_one()
        ev = (await db.execute(select(CaseEvent))).scalar_one()
    assert case.business_id == a_id and case.customer_id == ca and case.department_id is not None
    assert (ev.actor_kind, ev.actor_user_id, ev.kind) == ("ai", None, "created")
    assert res.data["case_id"] == str(case.id)


async def test_a_customer_from_another_business_is_refused_and_nothing_is_stored(env):
    factory, a_id, b_id, ca, cb = await setup(env)
    res = await run(gateway(factory, cb), a_id, "create_case", {"title": "Late parcel"})  # resolver returns Beta's customer
    assert not res.ok
    async with factory() as db:
        assert (await db.execute(select(Case))).scalars().all() == []


async def test_a_department_from_another_business_does_not_exist(env):
    factory, a_id, *_ , ca, cb = await setup(env)
    res = await run(gateway(factory, ca), a_id, "create_case", {"title": "Late parcel", "department": "Sales"})
    assert not res.ok and "Available: Delivery" in res.summary and "Sales" not in res.summary.split("Available:")[1]


async def test_unidentified_caller_cannot_log_a_case(env):
    factory, a_id, *_ = await setup(env)
    res = await run(gateway(factory, None), a_id, "create_case", {"title": "Late parcel"})
    assert not res.ok and "not been identified" in res.summary
    async with factory() as db:
        assert (await db.execute(select(Case))).scalars().all() == []


async def test_escalation_creates_an_urgent_case_when_the_caller_is_known(env):
    factory, a_id, b_id, ca, cb = await setup(env)
    res = await run(gateway(factory, ca), a_id, "escalate_to_human", {"reason": "wants a person"})
    assert res.ok and res.data["escalated"] is True
    async with factory() as db:
        case = (await db.execute(select(Case))).scalar_one()
    assert case.priority == "urgent" and case.business_id == a_id
    unknown = await run(gateway(factory, None), a_id, "escalate_to_human", {"reason": "wants a person"})
    assert unknown.ok and "case_id" not in unknown.data


async def test_only_offered_tools_run_and_bad_arguments_do_nothing(env):
    factory, a_id, *_ , ca, cb = await setup(env)
    gw = gateway(factory, ca)
    assert {t.name for t in await gw.list_tools(a_id, None)} == {"search_knowledge", "create_case", "escalate_to_human"}
    assert (await run(gw, a_id, "drop_tables", {})).summary == "That action is not available."
    assert (await run(gw, a_id, "run_sql", {"q": "x"})).ok is False
    assert not (await run(gw, a_id, "create_case", {"title": ""})).ok
    async with factory() as db:
        assert (await db.execute(select(Case))).scalars().all() == []
