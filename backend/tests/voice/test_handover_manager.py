from uuid import uuid4

from app.core.config import Settings
from app.services.voice.conversation_manager import MAX_HANDOVERS, ConversationManager
from app.services.voice.interfaces import ToolCallRequested, ToolDefinition, ToolResult
from app.services.voice.interfaces.business_tools import BusinessToolGateway
from app.services.voice.language_manager import LanguageManager
from app.services.voice.prompts import build_system_prompt
from app.services.voice.session_store import InMemorySessionStore
from tests.voice.test_conversation_manager import FakeReasoning, FakeTTS, TextDelta, done, say

TOOL = "hand_over_to_department_assistant"


class Gw(BusinessToolGateway):
    def __init__(self, ok=True):
        self.ok, self.calls = ok, 0

    async def list_tools(self, business_id, agent_id):
        return [ToolDefinition(name=TOOL, description="x", parameters={})]

    async def execute(self, *, business_id, session_id, tool_name, arguments):
        self.calls += 1
        if not self.ok:
            return ToolResult(ok=False, summary="That department does not exist.")
        return ToolResult(ok=True, summary="now with Sales", data={"department": "Sales", "focus": "You are now the Sales assistant. Order A123."})


def make(rounds, gw):
    s = Settings(_env_file=None)
    store = InMemorySessionStore(s)
    session = store.create(uuid4(), voice_id="v")
    reasoning = FakeReasoning(rounds)
    mgr = ConversationManager(s, reasoning, FakeTTS(), gw, LanguageManager(s))
    return mgr, session, reasoning


def call(i="c1"):
    return [ToolCallRequested(call_id=i, tool_name=TOOL, arguments={"department": "Sales"})]


async def sink(chunk):
    pass


async def test_successful_handover_changes_who_speaks_for_the_rest_of_the_call():
    mgr, session, reasoning = make([call(), [TextDelta(text="Hi, I'm the Sales assistant."), done()], [TextDelta(text="Sure."), done()]], Gw())
    await say(mgr, session, sink)
    assert session.active_department == "Sales" and session.handovers == 1
    assert reasoning.requests[0].department_focus is None
    assert "Sales assistant" in reasoning.requests[1].department_focus      # same turn, next round
    await say(mgr, session, sink, "More")
    assert "Order A123" in reasoning.requests[2].department_focus            # next turn keeps it


async def test_failed_handover_changes_nothing():
    mgr, session, reasoning = make([call(), [TextDelta(text="I could not."), done()]], Gw(ok=False))
    await say(mgr, session, sink)
    assert session.active_department is None and session.department_focus is None and session.handovers == 0
    assert reasoning.requests[1].department_focus is None


async def test_handovers_are_limited_per_call():
    gw = Gw()
    mgr, session, _ = make([], gw)
    session.handovers = MAX_HANDOVERS
    mgr._reasoning.rounds = [call(), [TextDelta(text="Ok."), done()]]
    await say(mgr, session, sink)
    assert gw.calls == 0 and session.handovers == MAX_HANDOVERS
    assert "too many times" in session.tool_history[-1].result_summary


def test_prompt_includes_department_focus_and_rules():
    p = build_system_prompt(business_context="Shop", language_name="English", department_focus="You are now the Sales assistant.")
    assert "You are now the Sales assistant." in p and "never say a person was connected" in p
    assert "Sales assistant" not in build_system_prompt(business_context="Shop", language_name="English")
