"""Department routing: hours, extensions, availability, fallback, callbacks, context, and the assistant's tools.
All telephony is SIMULATED (MockTelephony). Every rule is also checked across two businesses."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select

from app.database.models import AuditEvent, CallbackRequest, Department, Employee
from app.services.telephony import TransferService
from app.services.telephony.context import HandoverContext
from app.services.telephony.interfaces import TransferOutcome as O
from app.services.telephony.mock import MockTelephony
from app.services.telephony.schedule import is_open, validate_hours
from app.services.telephony.transfer import Decision
from app.services.voice.database_gateway import DatabaseBusinessGateway
from tests.api.test_customers_cases import API, add_user, login, two

# Monday 2026-11-23 at 10:00 UTC (Accra and UTC are the same all year)
MON_10 = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)
MON_20 = datetime(2026, 11, 23, 20, 0, tzinfo=timezone.utc)
OFFICE = {"mon": [["08:00", "17:00"]], "tue": [["08:00", "17:00"]]}


# ------------------------------------------------------------------ hours (pure)
def test_hours_rules():
    assert is_open(None, "UTC", MON_20)                       # no hours = always open
    assert is_open(OFFICE, "Africa/Accra", MON_10) and not is_open(OFFICE, "Africa/Accra", MON_20)
    assert not is_open(OFFICE, "UTC", datetime(2026, 11, 25, 10, 0, tzinfo=timezone.utc))  # Wednesday is missing = closed
    assert not is_open({}, "UTC", MON_10)                     # {} = closed every day
    assert is_open(OFFICE, "UTC", datetime(2026, 11, 23, 8, 0, tzinfo=timezone.utc))        # start is open
    assert not is_open(OFFICE, "UTC", datetime(2026, 11, 23, 17, 0, tzinfo=timezone.utc))   # end is closed
    # the same instant is a different local time elsewhere: 10:00 UTC is 05:00 in New York, so still closed there
    assert not is_open(OFFICE, "America/New_York", MON_10)
    assert not is_open({"mon": [["9", "17"]]}, "UTC", MON_10)  # unreadable stored hours never claim anyone is there


def test_hours_validation_messages():
    assert validate_hours(None) is None and validate_hours(OFFICE) is None
    assert "Unknown day" in validate_hours({"monday": [["08:00", "09:00"]]})
    assert "end after" in validate_hours({"mon": [["09:00", "08:00"]]})
    assert "overlap" in validate_hours({"mon": [["08:00", "12:00"], ["11:00", "13:00"]]})
    assert "08:00" in validate_hours({"mon": [["8am", "5pm"]]})
    assert validate_hours({"mon": [["08:00", "09:00"]] * 5})


# ------------------------------------------------------------------ routing service
async def build(env, *, a_hours=None, with_fallback=True):
    a, a_id, b, b_id, factory = await two(env)
    await a.aclose(); await b.aclose()
    async with factory() as db:
        sales = Department(business_id=a_id, name="Sales")
        accounts = Department(business_id=a_id, name="Accounts", hours=a_hours)
        other = Department(business_id=b_id, name="Accounts")
        db.add_all([sales, accounts, other]); await db.flush()
        if with_fallback:
            accounts.fallback_department_id = sales.id
        db.add_all([
            Employee(business_id=a_id, department_id=accounts.id, full_name="Acc One", phone="+233200000001", extension="101", routing_priority=20),
            Employee(business_id=a_id, department_id=accounts.id, full_name="Acc Two", phone="+233200000002", routing_priority=10),
            Employee(business_id=a_id, department_id=accounts.id, full_name="Away", phone="+233200000003", available=False, routing_priority=1),
            Employee(business_id=a_id, department_id=sales.id, full_name="Sales One", phone="+233200000010"),
            Employee(business_id=b_id, department_id=other.id, full_name="Other", phone="+233209999999"),
        ])
        await db.commit()
    return factory, a_id, b_id, sales.id, accounts.id, other.id


async def route(factory, svc, biz, dept, **kw):
    async with factory() as db:
        return await svc.transfer_to_department(db, biz, dept, "call-1", "payment_complaint", now=kw.pop("now", MON_10), **kw)


async def audit_rows(factory):
    async with factory() as db:
        return list((await db.execute(select(AuditEvent).where(AuditEvent.action == "call.transfer"))).scalars())


async def test_staff_are_tried_by_priority_and_unavailable_staff_are_skipped(env):
    p = MockTelephony()
    factory, a_id, _, _, accounts, _ = await build(env)
    d = await route(factory, TransferService(p), a_id, accounts)
    assert d.connected and p.attempts == [("call-1", "+233200000002")]  # priority 10 first; "Away" (priority 1) is not available


async def test_extension_is_passed_to_the_provider(env):
    seen = []

    class Spy(MockTelephony):
        async def transfer_call(self, call_ref, target):
            seen.append((target.phone, target.extension))
            return await super().transfer_call(call_ref, target)
    factory, a_id, _, _, accounts, _ = await build(env)
    await route(factory, TransferService(Spy({"+233200000002": O.NO_ANSWER})), a_id, accounts)
    assert seen == [("+233200000002", None), ("+233200000001", "101")]


async def test_closed_department_uses_its_fallback_and_says_so(env):
    p = MockTelephony()
    factory, a_id, _, sales, accounts, _ = await build(env, a_hours=OFFICE)
    d = await route(factory, TransferService(p), a_id, accounts, now=MON_20)
    assert d.connected and d.fallback_used and d.department_id == sales and p.attempts == [("call-1", "+233200000010")]
    assert d.reasons == ("closed",)


async def test_closed_without_fallback_offers_a_callback_and_dials_nobody(env):
    p = MockTelephony()
    factory, a_id, _, _, accounts, _ = await build(env, a_hours=OFFICE, with_fallback=False)
    d = await route(factory, TransferService(p), a_id, accounts, now=MON_20)
    assert d.decision is Decision.DEPARTMENT_CLOSED and d.next_step == "offer_callback" and not d.connected and p.attempts == []


async def test_department_not_accepting_transfers_is_skipped(env):
    p = MockTelephony()
    factory, a_id, _, sales, accounts, _ = await build(env)
    async with factory() as db:
        (await db.get(Department, accounts)).accepts_transfers = False
        await db.commit()
    d = await route(factory, TransferService(p), a_id, accounts)
    assert d.connected and d.fallback_used and d.reasons == ("not_accepting",)


async def test_unanswered_calls_fall_through_to_the_fallback_within_one_shared_budget(env):
    p = MockTelephony(default=O.NO_ANSWER)
    factory, a_id, _, _, accounts, _ = await build(env)
    d = await route(factory, TransferService(p), a_id, accounts)
    assert not d.connected and d.decision is Decision.ALL_ATTEMPTS_FAILED and d.attempts == 3 == len(p.attempts)  # 2 in Accounts + 1 in Sales, never more


async def test_fallback_loops_are_cut(env):
    p = MockTelephony(default=O.NO_ANSWER)
    factory, a_id, _, sales, accounts, _ = await build(env)
    async with factory() as db:
        (await db.get(Department, sales)).fallback_department_id = accounts  # Accounts -> Sales -> Accounts
        await db.commit()
    d = await route(factory, TransferService(p, max_attempts=10), a_id, accounts)
    assert len(d.tried) == 2 and len(set(d.tried)) == 2


async def test_unconfirmed_is_never_success(env):
    factory, a_id, _, _, accounts, _ = await build(env)
    d = await route(factory, TransferService(MockTelephony(default=O.UNCONFIRMED)), a_id, accounts)
    assert not d.connected and d.next_step == "offer_callback"


async def test_other_business_department_and_fallback_are_unreachable(env):
    p = MockTelephony()
    factory, a_id, b_id, sales, accounts, other = await build(env)
    d = await route(factory, TransferService(p), a_id, other)
    assert d.decision is Decision.UNKNOWN_DEPARTMENT and p.attempts == [] and await audit_rows(factory) == []
    async with factory() as db:  # a bad row pointing at another business must not be followed
        (await db.get(Department, accounts)).fallback_department_id = other
        (await db.get(Department, accounts)).accepts_transfers = False
        await db.commit()
    d = await route(factory, TransferService(p), a_id, accounts)
    assert not d.connected and p.attempts == [] and other not in d.tried


async def test_context_is_returned_for_the_receiver_but_never_written_to_the_audit_log(env):
    factory, a_id, _, _, accounts, _ = await build(env)
    ctx = HandoverContext(intent="Overcharged invoice", summary="Customer says invoice 4471 doubled", collected={"invoice": "4471", "name": "Efua"},
                          done=["Checked policy"], open_questions=["Wants refund or credit?"])
    d = await route(factory, TransferService(MockTelephony()), a_id, accounts, context=ctx)
    assert "4471" in d.briefing and "Efua" in d.briefing and "Wants refund or credit?" in d.briefing
    detail = str((await audit_rows(factory))[0].detail)
    assert "4471" not in detail and "Efua" not in detail and "+233" not in detail and "Acc" not in detail
    assert (await audit_rows(factory))[0].detail["had_context"] is True


async def test_context_limits():
    import pytest
    with pytest.raises(ValueError):
        HandoverContext(collected={f"k{i}": "v" for i in range(21)})
    with pytest.raises(ValueError):
        HandoverContext(collected={"k": "v" * 201})


# ------------------------------------------------------------------ API: departments and employees
async def test_department_routing_settings_api(env):
    a, a_id, b, b_id, factory = await two(env)
    d1 = (await a.post(f"{API}/departments", json={"name": "Sales"})).json()
    d2 = (await a.post(f"{API}/departments", json={"name": "Accounts", "hours": OFFICE, "timezone": "Africa/Accra", "fallback_department_id": d1["id"]})).json()
    assert d2["hours"] == OFFICE and d2["fallback_department_id"] == d1["id"] and d2["accepts_transfers"] is True
    other = (await b.post(f"{API}/departments", json={"name": "Foreign"})).json()
    # invalid inputs
    assert (await a.patch(f"{API}/departments/{d2['id']}", json={"hours": {"mon": [["9", "5"]]}})).status_code == 422
    assert (await a.patch(f"{API}/departments/{d2['id']}", json={"timezone": "Mars/Base"})).status_code == 422
    assert (await a.patch(f"{API}/departments/{d2['id']}", json={"fallback_department_id": d2["id"]})).status_code == 422
    assert (await a.patch(f"{API}/departments/{d2['id']}", json={"fallback_department_id": other["id"]})).status_code == 422  # another business's department
    assert (await a.patch(f"{API}/departments/{d2['id']}", json={"accepts_transfers": None})).status_code == 422
    # another business cannot read or change it
    assert (await b.patch(f"{API}/departments/{d2['id']}", json={"hours": None})).status_code == 404
    assert (await b.get(f"{API}/departments/{d2['id']}/availability")).status_code == 404
    # clearing hours = always open
    r = await a.patch(f"{API}/departments/{d2['id']}", json={"hours": None})
    assert r.json()["hours"] is None
    # permission
    await add_user(factory, a_id, "Reader", ["departments:read"], "r@a.test")
    r = await login(env, "r@a.test")
    assert (await r.patch(f"{API}/departments/{d2['id']}", json={"accepts_transfers": False})).status_code == 403
    assert (await r.get(f"{API}/departments/{d2['id']}/availability")).status_code == 200


async def test_availability_counts_only_reachable_staff(env):
    a, a_id, b, b_id, factory = await two(env)
    d = (await a.post(f"{API}/departments", json={"name": "Accounts"})).json()
    base = {"department_id": d["id"]}
    await a.post(f"{API}/employees", json={"full_name": "Ama Boateng", "phone": "+233200000001", **base})
    await a.post(f"{API}/employees", json={"full_name": "Kofi Away", "phone": "+233200000002", "available": False, **base})
    await a.post(f"{API}/employees", json={"full_name": "No Phone", **base})
    r = (await a.get(f"{API}/departments/{d['id']}/availability")).json()
    assert r["reachable_staff"] == 1 and r["open_now"] is True and r["can_transfer_now"] is True
    assert "Ama" not in str(r) and "+233" not in str(r)
    await a.patch(f"{API}/departments/{d['id']}", json={"hours": {}})
    r = (await a.get(f"{API}/departments/{d['id']}/availability")).json()
    assert r["open_now"] is False and r["can_transfer_now"] is False


async def test_employee_extension_and_priority_api(env):
    a, a_id, b, b_id, factory = await two(env)
    e = (await a.post(f"{API}/employees", json={"full_name": "Ama Boateng", "extension": "204", "routing_priority": 5})).json()
    assert e["extension"] == "204" and e["routing_priority"] == 5 and e["available"] is True
    assert (await a.patch(f"{API}/employees/{e['id']}", json={"extension": "12 ab"})).status_code == 422
    assert (await a.patch(f"{API}/employees/{e['id']}", json={"routing_priority": 0})).status_code == 422
    assert (await a.patch(f"{API}/employees/{e['id']}", json={"available": None})).status_code == 422
    assert (await a.patch(f"{API}/employees/{e['id']}", json={"available": False})).json()["available"] is False
    assert (await b.patch(f"{API}/employees/{e['id']}", json={"available": True})).status_code == 404


# ------------------------------------------------------------------ API: callbacks
async def test_callbacks_api_isolation_permissions_and_rules(env):
    a, a_id, b, b_id, factory = await two(env)
    dept = (await a.post(f"{API}/departments", json={"name": "Accounts"})).json()
    foreign = (await b.post(f"{API}/departments", json={"name": "Foreign"})).json()
    body = {"phone": "+233 20 000 0000", "reason": "Invoice query", "department_id": dept["id"], "context": {"intent": "invoice", "collected": {"invoice": "4471"}}}
    r = await a.post(f"{API}/callbacks", json=body)
    assert r.status_code == 201 and r.json()["status"] == "pending" and r.json()["source"] == "staff" and r.json()["context"]["collected"] == {"invoice": "4471"}
    cb = r.json()
    # input rules
    assert (await a.post(f"{API}/callbacks", json={**body, "phone": "call me"})).status_code == 422
    assert (await a.post(f"{API}/callbacks", json={**body, "department_id": foreign["id"]})).status_code == 422
    assert (await a.post(f"{API}/callbacks", json={**body, "customer_id": str(uuid4())})).status_code == 422
    assert (await a.post(f"{API}/callbacks", json={**body, "extra": 1})).status_code == 422
    # isolation
    assert (await b.get(f"{API}/callbacks")).json()["total"] == 0
    assert (await b.patch(f"{API}/callbacks/{cb['id']}", json={"status": "done"})).status_code == 404
    assert (await a.get(f"{API}/callbacks")).json()["total"] == 1
    # permissions
    await add_user(factory, a_id, "Nobody", ["customers:read"], "n@a.test")
    n = await login(env, "n@a.test")
    assert (await n.get(f"{API}/callbacks")).status_code == 403
    assert (await n.post(f"{API}/callbacks", json=body)).status_code == 403
    await add_user(factory, a_id, "Viewer", ["cases:read"], "v@a.test")
    v = await login(env, "v@a.test")
    assert (await v.get(f"{API}/callbacks")).status_code == 200
    assert (await v.patch(f"{API}/callbacks/{cb['id']}", json={"status": "contacted"})).status_code == 403
    # status rules
    assert (await a.patch(f"{API}/callbacks/{cb['id']}", json={"status": "contacted", "note": "Left a voicemail"})).json()["note"] == "Left a voicemail"
    assert (await a.patch(f"{API}/callbacks/{cb['id']}", json={"status": "done"})).json()["status"] == "done"
    assert (await a.patch(f"{API}/callbacks/{cb['id']}", json={"status": "pending"})).status_code == 422  # finished requests stay finished
    # audit has ids only, never the number
    async with factory() as db:
        events = (await db.execute(select(AuditEvent).where(AuditEvent.action.like("callback.%")))).scalars().all()
    assert len(events) == 3 and "+233" not in str([e.detail for e in events]) and "4471" not in str([e.detail for e in events])


# ------------------------------------------------------------------ the assistant's tools
async def gateway(env, provider=None, **build_kw):
    factory, a_id, b_id, sales, accounts, other = await build(env, **build_kw)

    async def nobody(_b, _s):
        return None
    svc = TransferService(provider or MockTelephony()) if provider is not False else None
    return DatabaseBusinessGateway(factory, nobody, svc), factory, a_id, b_id


async def call(gw, biz, tool, args):
    return await gw.execute(business_id=biz, session_id=uuid4(), tool_name=tool, arguments=args)


async def test_transfer_tool_is_honest_that_it_is_simulated(env):
    gw, factory, a_id, *_ = await gateway(env)
    r = await call(gw, a_id, "transfer_to_department", {"department": "accounts", "context": {"intent": "invoice"}})
    assert r.ok and r.data["simulated"] is True and "SIMULATED" in r.summary and "Do not tell the caller they are now connected" in r.summary


async def test_transfer_tool_failures_say_nothing_was_transferred(env):
    gw, factory, a_id, *_ = await gateway(env, MockTelephony(default=O.NO_ANSWER))
    r = await call(gw, a_id, "transfer_to_department", {"department": "Accounts"})
    assert not r.ok and "Nothing was transferred" in r.summary and "request_callback" in r.summary


async def test_transfer_tool_unknown_or_foreign_department(env):
    gw, factory, a_id, *_ = await gateway(env)
    r = await call(gw, a_id, "transfer_to_department", {"department": "Foreign Dept"})
    assert not r.ok and "Available: Accounts, Sales" in r.summary
    assert (await call(gw, uuid4(), "transfer_to_department", {"department": "Accounts"})).ok is False  # a business with no departments


async def test_no_transfer_tool_without_a_transfer_service(env):
    gw, _, a_id, *_ = await gateway(env, False)
    assert "transfer_to_department" not in {t.name for t in await gw.list_tools(a_id, None)}
    assert not (await call(gw, a_id, "transfer_to_department", {"department": "Accounts"})).ok


async def test_callback_tool_records_for_the_right_business_and_never_promises_a_time(env):
    gw, factory, a_id, b_id = await gateway(env)
    r = await call(gw, a_id, "request_callback", {"phone": "+233200000099", "reason": "Wants a refund update", "department": "accounts",
                                                   "context": {"intent": "refund", "open_questions": ["Which invoice?"]}})
    assert r.ok and "not a booked time" in r.summary
    async with factory() as db:
        row = (await db.execute(select(CallbackRequest))).scalar_one()
    assert row.business_id == a_id and row.source == "ai" and row.department_id is not None and row.context["intent"] == "refund"
    bad = await call(gw, a_id, "request_callback", {"phone": "later", "reason": "x y"})
    assert not bad.ok and "Nothing was recorded" in bad.summary
    foreign = await call(gw, a_id, "request_callback", {"phone": "+233200000099", "reason": "x y", "department": "Foreign Dept"})
    assert not foreign.ok
    async with factory() as db:
        assert len((await db.execute(select(CallbackRequest))).scalars().all()) == 1


async def test_prompt_states_the_transfer_and_callback_rules():
    from app.services.voice.prompts import SAFETY_RULES
    assert "only if its result says the provider confirmed it" in SAFETY_RULES and "not a booked time" in SAFETY_RULES
