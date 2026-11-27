"""Whole simulated calls: scripted model -> conversation manager -> real database gateway -> routing -> mock telephony.
No provider, no network, no real call. Checks what the assistant is told, what is stored, and what never leaks."""

from uuid import uuid4

from sqlalchemy import select

from app.core.config import Settings
from app.database.models import AuditEvent, CallbackRequest, Department, Employee
from app.services.telephony import TransferService
from app.services.telephony.interfaces import TransferOutcome as O
from app.services.telephony.mock import MockTelephony
from app.services.voice.conversation_manager import ConversationManager
from app.services.voice.database_gateway import DatabaseBusinessGateway
from app.services.voice.interfaces import ToolCallRequested
from app.services.voice.language_manager import LanguageManager
from app.services.voice.session_store import InMemorySessionStore
from tests.api.test_customers_cases import two
from tests.voice.test_conversation_manager import FakeReasoning, FakeTTS, TextDelta, done

CTX = {"intent": "Invoice dispute", "summary": "Invoice 77 charged twice.", "collected": {"invoice": "77"}, "open_questions": ["Refund timing"]}


async def world(env, *, accounts_hours=None, outcome=O.CONFIRMED):
    a, a_id, b, b_id, factory = await two(env)
    await a.aclose(); await b.aclose()
    async with factory() as db:
        sales = Department(business_id=a_id, name="Sales")
        accounts = Department(business_id=a_id, name="Accounts", hours=accounts_hours)
        other = Department(business_id=b_id, name="Accounts")
        db.add_all([sales, accounts, other]); await db.flush()
        db.add_all([Employee(business_id=a_id, department_id=accounts.id, full_name="Acc One", phone="+233200000001"),
                    Employee(business_id=b_id, department_id=other.id, full_name="Other", phone="+233209999999")])
        await db.commit()
    telephony = MockTelephony(default=outcome)

    async def nobody(biz, sid):
        return None

    gw = DatabaseBusinessGateway(factory, nobody, TransferService(telephony))
    return factory, a_id, b_id, telephony, gw


def call(name, args, i="c1"):
    return [ToolCallRequested(call_id=i, tool_name=name, arguments=args)]


def say_script(text):
    return [TextDelta(text=text), done()]


async def run_call(gw, biz, rounds, utterances=("Hello",)):
    s = Settings(_env_file=None)
    session = InMemorySessionStore(s).create(biz, voice_id="v")
    reasoning = FakeReasoning(rounds)
    mgr = ConversationManager(s, reasoning, FakeTTS(), gw, LanguageManager(s))

    async def sink(chunk):
        pass

    for u in utterances:
        await mgr.handle_utterance(session, u, sink, business_context="Alpha")
    return session, reasoning


def results(reasoning):
    return [ex.result for r in reasoning.requests for ex in r.tool_exchanges]


async def test_open_department_transfer_is_reported_as_simulated_never_as_connected(env):
    factory, a_id, b_id, telephony, gw = await world(env)
    session, reasoning = await run_call(gw, a_id, [call("transfer_to_department", {"department": "Accounts", "reason": "invoice", "context": CTX}), say_script("Okay.")])
    res = results(reasoning)[-1]
    assert res.ok and res.data["simulated"] is True
    assert "SIMULATED" in res.summary and "Do not tell the caller they are now connected" in res.summary
    assert [p for _, p in telephony.attempts] == ["+233200000001"]          # only this business's staff were dialled
    async with factory() as db:
        assert (await db.execute(select(CallbackRequest))).scalars().all() == []
        blob = str([e.detail for e in (await db.execute(select(AuditEvent).where(AuditEvent.action == "call.transfer"))).scalars().all()])
    for private in ("+233200000001", "233200000001", "Acc One", "Invoice dispute", "Invoice 77", "charged twice"):
        assert private not in blob, private


async def test_closed_department_leads_to_a_callback_that_keeps_the_context(env):
    factory, a_id, b_id, telephony, gw = await world(env, accounts_hours={})
    rounds = [call("transfer_to_department", {"department": "Accounts", "context": CTX}),
              call("request_callback", {"phone": "+233 24 555 0000", "reason": "Invoice dispute", "department": "Accounts", "caller_name": "Esi", "context": CTX}, "c2"),
              say_script("I have passed on a request. Someone will phone you.")]
    session, reasoning = await run_call(gw, a_id, rounds)
    first, second = results(reasoning)[0], results(reasoning)[-1]
    assert not first.ok and "closed" in first.summary and "callback" in first.summary and "Nothing was transferred" in first.summary
    assert telephony.attempts == []                                          # nobody was dialled while closed
    assert second.ok and "not a booked time" in second.summary
    async with factory() as db:
        cb = (await db.execute(select(CallbackRequest))).scalar_one()
    assert cb.business_id == a_id and cb.status == "pending" and cb.source == "ai"
    assert cb.context["collected"] == {"invoice": "77"} and cb.context["intent"] == "Invoice dispute"
    assert [t.tool_name for t in session.tool_history] == ["transfer_to_department", "request_callback"]


async def test_unconfirmed_provider_never_counts_as_a_transfer(env):
    factory, a_id, b_id, telephony, gw = await world(env, outcome=O.UNCONFIRMED)
    _, reasoning = await run_call(gw, a_id, [call("transfer_to_department", {"department": "Accounts"}), say_script("Sorry.")])
    res = results(reasoning)[-1]
    assert not res.ok and "Nothing was transferred" in res.summary and "connected" not in res.summary.replace("Nothing", "")


async def test_handover_then_callback_in_one_call(env):
    factory, a_id, b_id, telephony, gw = await world(env)
    rounds = [call("hand_over_to_department_assistant", {"department": "Accounts", "reason": "invoice", "context": CTX}),
              call("request_callback", {"phone": "+233245550000", "reason": "Refund timing", "department": "Accounts"}, "c2"),
              say_script("Done.")]
    session, reasoning = await run_call(gw, a_id, rounds)
    assert session.active_department == "Accounts" and session.handovers == 1
    assert "Invoice 77 charged twice." in reasoning.requests[1].department_focus      # the next model round already has the briefing
    assert reasoning.requests[0].department_focus is None
    assert telephony.attempts == []                                                   # a hand-over is not a phone call
    async with factory() as db:
        assert (await db.execute(select(CallbackRequest))).scalar_one().department_id is not None


async def test_other_business_sees_nothing_and_cannot_be_reached(env):
    factory, a_id, b_id, telephony, gw = await world(env, accounts_hours={})
    await run_call(gw, a_id, [call("request_callback", {"phone": "+233245550000", "reason": "x1", "department": "Accounts"}), say_script("ok")])
    _, reasoning = await run_call(gw, b_id, [call("hand_over_to_department_assistant", {"department": "Sales"}), say_script("ok")])
    assert not results(reasoning)[-1].ok                                              # Sales exists only in business A
    async with factory() as db:
        rows = (await db.execute(select(CallbackRequest))).scalars().all()
    assert [r.business_id for r in rows] == [a_id]
