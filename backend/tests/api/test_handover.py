from sqlalchemy import select

from app.database.models import AuditEvent, Department
from tests.api.test_voice_database_gateway import gateway, run, setup

CTX = {"intent": "Late parcel", "summary": "Parcel A123 is three days late.", "collected": {"order": "A123"}, "done": ["Checked tracking"], "open_questions": ["New delivery date"]}


async def test_handover_briefs_the_department_assistant_without_claiming_a_person(env):
    factory, a_id, b_id, ca, cb = await setup(env)
    res = await run(gateway(factory, ca), a_id, "hand_over_to_department_assistant", {"department": "delivery", "reason": "Needs delivery help", "context": CTX})
    assert res.ok and res.data["department"] == "Delivery"
    focus = res.data["focus"]
    for want in ("Delivery assistant", "Needs delivery help", "A123", "Checked tracking", "must not be asked"):
        assert want in focus, want
    assert "not a person" in res.summary and "do not say a person was connected" in res.summary


async def test_handover_never_reaches_another_business(env):
    factory, a_id, b_id, ca, cb = await setup(env)
    res = await run(gateway(factory, ca), a_id, "hand_over_to_department_assistant", {"department": "Sales"})   # Sales belongs to Beta
    assert not res.ok and "focus" not in res.data and "Available: Delivery" in res.summary
    assert "Sales" not in res.summary.split("Available:")[1]
    ok = await run(gateway(factory, cb), b_id, "hand_over_to_department_assistant", {"department": "Sales"})
    assert ok.ok and "Delivery" not in ok.data["focus"]


async def test_handover_rejects_bad_arguments_and_stores_nothing(env):
    factory, a_id, *_ , ca, cb = await setup(env)
    for bad in ({}, {"department": "D"}, {"department": "Delivery", "extra": 1}, {"department": "Delivery", "context": {"collected": {"k": "v" * 201}}}):
        assert not (await run(gateway(factory, ca), a_id, "hand_over_to_department_assistant", bad)).ok, bad
    async with factory() as db:
        assert (await db.execute(select(AuditEvent))).scalars().all() == []


async def test_department_description_reaches_the_briefing(env):
    factory, a_id, *_ , ca, cb = await setup(env)
    async with factory() as db:
        d = (await db.execute(select(Department).where(Department.business_id == a_id))).scalar_one()
        d.description = "Handles parcels and drivers."
        await db.commit()
    res = await run(gateway(factory, ca), a_id, "hand_over_to_department_assistant", {"department": "Delivery"})
    assert "Handles parcels and drivers." in res.data["focus"]
