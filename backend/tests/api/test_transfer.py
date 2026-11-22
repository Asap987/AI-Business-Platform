from sqlalchemy import select

from app.database.models import AuditEvent, Department, Employee
from app.services.telephony import TransferService
from app.services.telephony.interfaces import TelephonyProvider, TransferOutcome, TransferResult
from app.services.telephony.mock import MockTelephony
from app.services.telephony.transfer import Decision
from tests.api.test_customers_cases import two

O = TransferOutcome


async def seed(factory, a_id, b_id):
    async with factory() as db:
        da, db_ = Department(business_id=a_id, name="Accounts"), Department(business_id=b_id, name="Accounts")
        db.add_all([da, db_]); await db.flush()
        db.add_all([
            Employee(business_id=a_id, department_id=da.id, full_name="Ama", phone="+233200000001"),
            Employee(business_id=a_id, department_id=da.id, full_name="Kofi", phone="+233200000002"),
            Employee(business_id=a_id, department_id=da.id, full_name="Off duty", phone="+233200000003", status="inactive"),
            Employee(business_id=a_id, department_id=da.id, full_name="No phone"),
            Employee(business_id=b_id, department_id=db_.id, full_name="Other", phone="+233209999999"),
        ])
        await db.commit()
        return da.id, db_.id


async def run(env, provider):
    a, a_id, b, b_id, factory = await two(env)
    await a.aclose(); await b.aclose()
    da, db_ = await seed(factory, a_id, b_id)
    return factory, a_id, b_id, da, db_, TransferService(provider)


async def audits(factory):
    async with factory() as db:
        return list((await db.execute(select(AuditEvent).where(AuditEvent.action == "call.transfer"))).scalars())


async def test_confirmed_transfer_uses_only_active_staff_of_that_department(env):
    p = MockTelephony()
    factory, a_id, _, da, _, svc = await run(env, p)
    async with factory() as db:
        d = await svc.transfer_to_department(db, a_id, da, "call-1", "payment_complaint")
    assert d.connected and d.next_step == "connected" and d.attempts == 1 and d.simulated is True
    assert p.attempts == [("call-1", "+233200000001")]  # inactive and phone-less staff never dialled
    ev = await audits(factory)
    assert len(ev) == 1 and ev[0].business_id == a_id and ev[0].detail["decision"] == "transferred"
    assert "+233" not in str(ev[0].detail) and "Ama" not in str(ev[0].detail)  # no numbers or names in the audit trail


async def test_failed_attempts_fall_through_then_offer_callback_never_claiming_success(env):
    p = MockTelephony({"+233200000001": O.NO_ANSWER, "+233200000002": O.UNCONFIRMED})
    factory, a_id, _, da, _, svc = await run(env, p)
    async with factory() as db:
        d = await svc.transfer_to_department(db, a_id, da, "c", "x")
    assert not d.connected and d.decision is Decision.ALL_ATTEMPTS_FAILED and d.next_step == "offer_callback" and d.attempts == 2
    assert (await audits(factory))[0].detail["outcomes"] == ["no_answer", "unconfirmed"]


async def test_second_person_can_answer_after_first_is_busy(env):
    p = MockTelephony({"+233200000001": O.BUSY})
    factory, a_id, _, da, _, svc = await run(env, p)
    async with factory() as db:
        d = await svc.transfer_to_department(db, a_id, da, "c", "x")
    assert d.connected and d.attempts == 2


async def test_other_businesses_department_is_unknown_and_nobody_is_dialled(env):
    p = MockTelephony()
    factory, a_id, _, _, db_, svc = await run(env, p)
    async with factory() as db:
        d = await svc.transfer_to_department(db, a_id, db_, "c", "x")
    assert d.decision is Decision.UNKNOWN_DEPARTMENT and d.next_step == "ask_which_department" and p.attempts == []
    assert await audits(factory) == []


async def test_department_with_nobody_reachable_offers_callback(env):
    p = MockTelephony()
    factory, a_id, b_id, _, _, svc = await run(env, p)
    async with factory() as db:
        empty = Department(business_id=a_id, name="Empty"); db.add(empty); await db.commit()
        d = await svc.transfer_to_department(db, a_id, empty.id, "c", "x")
    assert d.decision is Decision.NOBODY_AVAILABLE and d.next_step == "offer_callback" and p.attempts == []


class Exploding(TelephonyProvider):
    name = "boom"

    async def transfer_call(self, call_ref, target):
        return TransferResult(O.FAILED)

    async def hang_up(self, call_ref): ...
    async def health_check(self): return True


async def test_real_provider_is_not_flagged_simulated_and_attempts_are_capped(env):
    factory, a_id, _, da, _, _ = await run(env, MockTelephony())
    svc = TransferService(Exploding(), max_attempts=1)
    async with factory() as db:
        d = await svc.transfer_to_department(db, a_id, da, "c", "x")
    assert d.simulated is False and d.attempts == 1 and not d.connected


async def test_employee_row_from_another_business_is_never_dialled_even_if_it_points_at_this_department(env):
    p = MockTelephony(default=O.NO_ANSWER)
    factory, a_id, b_id, da, _, svc = await run(env, p)
    async with factory() as db:
        db.add(Employee(business_id=b_id, department_id=da, full_name="Stray", phone="+233208888888"))
        await db.commit()
        await svc.transfer_to_department(db, a_id, da, "c", "x")
    assert "+233208888888" not in [ph for _, ph in p.attempts]
