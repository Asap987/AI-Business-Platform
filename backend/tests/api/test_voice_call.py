import asyncio
import json
import logging

from app.api.v1.voice import test_call as voice_test_call
from app.core.config import Settings
from app.database.models import Agent
from app.services.voice.business_gateway import BusinessData, InMemoryBusinessGateway
from app.services.voice.conversation_manager import ConversationManager
from app.services.voice.database_gateway import DatabaseBusinessGateway
from app.services.voice.errors import ProviderError
from app.services.voice.interfaces import SpeechToText, STTStream, TextDelta, TurnCompleted, ReasoningUsage
from app.services.voice.language_manager import LanguageManager
from app.services.voice.privacy import ProviderControls
from app.services.voice.schemas.transcription import TranscriptEvent
from app.services.voice.session_store import InMemorySessionStore
from app.services.voice.stack import VoiceStack, build_voice_stack, missing_for_live_voice
from tests.api.conftest import ORIGIN
from tests.api.test_customers_cases import add_user, login, two
from tests.voice.test_conversation_manager import FakeReasoning, FakeTTS, done

CUSTOMER_WORDS = "my-private-question-about-parcels"


class FakeStream(STTStream):
    def __init__(self, script, fail=None):
        self.script, self.fail, self.audio, self.closed = list(script), fail, [], False
        self.q: asyncio.Queue = asyncio.Queue()

    async def send_audio(self, chunk):
        self.audio.append(chunk)
        if len(self.audio) == 1:  # the customer's first audio triggers the scripted recognition
            for ev in self.script:
                self.q.put_nowait(ev)

    async def events(self):
        while True:
            ev = await self.q.get()
            if ev is None:
                return
            if isinstance(ev, Exception):
                raise ev
            yield ev

    async def close(self):
        self.closed = True
        self.q.put_nowait(None)


class FakeSTT(SpeechToText):
    def __init__(self, script=(), open_error=None):
        self.script, self.open_error, self.stream = script, open_error, None

    async def open_stream(self, config):
        if self.open_error:
            raise self.open_error
        self.stream = FakeStream(self.script)
        return self.stream

    async def health_check(self):
        return True


class FakeWS:
    def __init__(self, app, *, origin=ORIGIN, cookie=None, query_agent=None):
        self.app, self.headers = app, ({"origin": origin} if origin else {})
        self.cookies = {app.state.settings.session_cookie_name: cookie} if cookie else {}
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.json, self.audio, self.accepted, self.closed = [], [], False, None

    async def accept(self): self.accepted = True
    async def send_text(self, t): self.json.append(json.loads(t))
    async def send_json(self, m): self.json.append(m)
    async def send_bytes(self, b): self.audio.append(b)
    async def close(self, code=1000):
        if self.closed is None:
            self.closed = code
    async def receive(self): return await self.inbox.get()
    def client_sends(self, *, data=None, text=None): self.inbox.put_nowait({"type": "websocket.receive", "bytes": data, "text": text})
    def hang_up(self): self.inbox.put_nowait({"type": "websocket.disconnect"})
    def types(self): return [m["type"] for m in self.json]


def stack_for(factory, settings, stt, rounds):
    languages = LanguageManager(settings)
    gw = DatabaseBusinessGateway(factory, lambda b, s: _none())
    mgr = ConversationManager(settings, FakeReasoning(rounds), FakeTTS(), gw, languages)
    return VoiceStack(stt, mgr, InMemorySessionStore(settings), ProviderControls(), languages)


async def _none():
    return None


def enable(env, stt=None, rounds=(), voice="voice-1", **cfg):
    app, factory, settings = env
    s = Settings(_env_file=None, environment="test", elevenlabs_default_voice_id=voice, **cfg)
    app.state.settings = s
    app.state.voice_stack = stack_for(factory, s, stt or FakeSTT(), list(rounds))
    return app.state.voice_stack


def final(text="what time do you open"):
    return TranscriptEvent(text=text, is_final=True, language_code="eng", language_probability=0.99)


async def settle(ws, predicate, timeout=3):
    for _ in range(int(timeout / 0.02)):
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"timed out; saw {ws.types()}")


async def call(env, cookie, **kw):
    ws = FakeWS(env[0], cookie=cookie, **kw)
    return ws, asyncio.create_task(voice_test_call(ws, kw.get("query_agent")))


async def test_refused_before_accept_for_bad_origin_no_cookie_and_missing_permission(env):
    a, a_id, b, _, factory = await two(env)
    enable(env)
    try:
        cookie = a.cookies.get(env[2].session_cookie_name)
        for ws in (FakeWS(env[0], origin="http://evil.test", cookie=cookie), FakeWS(env[0], origin=None, cookie=cookie), FakeWS(env[0], cookie=None),
                   FakeWS(env[0], cookie="not-a-real-session")):
            await voice_test_call(ws, None)
            assert ws.closed == 1008 and not ws.accepted and ws.json == []
        await add_user(factory, a_id, "Reader", ["cases:read"], "r@a.test")
        r = await login(env, "r@a.test")
        ws = FakeWS(env[0], cookie=r.cookies.get(env[2].session_cookie_name))
        await voice_test_call(ws, None)
        assert ws.closed == 1008 and not ws.accepted
        await r.aclose()
    finally:
        await a.aclose(), await b.aclose()


async def test_not_enabled_or_not_configured_says_why(env):
    a, a_id, b, _, factory = await two(env)
    try:
        cookie = a.cookies.get(env[2].session_cookie_name)
        env[0].state.voice_stack = None  # the default: off
        ws = FakeWS(env[0], cookie=cookie); await voice_test_call(ws, None)
        assert ws.accepted and ws.json == [{"type": "error", "code": "voice_not_enabled"}] and ws.closed == 1013
        enable(env, voice=None)
        ws = FakeWS(env[0], cookie=cookie); await voice_test_call(ws, None)
        assert ws.json == [{"type": "error", "code": "no_voice_configured"}]
        enable(env, stt=FakeSTT(open_error=ProviderError("elevenlabs", "auth", "x", recoverable=False)))
        ws = FakeWS(env[0], cookie=cookie); await voice_test_call(ws, None)
        assert ws.json == [{"type": "error", "code": "speech_unavailable_auth"}]
        assert env[0].state.voice_stack.store.active_count(a_id) == 0
    finally:
        await a.aclose(), await b.aclose()


async def test_full_call_answers_from_knowledge_and_keeps_nothing(env, caplog):
    a, a_id, b, _, factory = await two(env)
    caplog.set_level(logging.DEBUG, logger="app")  # our own loggers; SQL drivers' debug output is a separate matter
    try:
        await a.post("/api/v1/knowledge", json={"title": "Opening hours", "content": "We open at eight in the morning."})
        stt = FakeSTT([final(CUSTOMER_WORDS)])
        from app.services.voice.interfaces import ToolCallRequested
        rounds = [[ToolCallRequested(call_id="c1", tool_name="search_knowledge", arguments={"query": "opening hours"})],
                  [TextDelta(text="We open at eight. Anything else?"), done()]]
        stack = enable(env, stt, rounds)
        ws, task = await call(env, a.cookies.get(env[2].session_cookie_name))
        await settle(ws, lambda: ws.accepted and "ready" in ws.types())
        ws.client_sends(data=b"\x00\x01" * 160)
        await settle(ws, lambda: any(m.get("speaker") == "assistant" for m in ws.json))
        assert {"type": "transcript", "speaker": "customer", "text": CUSTOMER_WORDS} in ws.json
        reply = [m for m in ws.json if m.get("speaker") == "assistant"][0]
        assert "We open at eight" in reply["text"] and ws.audio  # audio went to the browser
        # the model was handed the stored document through the tool, scoped to this business
        second_request = stack.manager._reasoning.requests[1]
        assert "open at eight in the morning" in second_request.tool_exchanges[0].result.summary
        ws.client_sends(text=json.dumps({"type": "end"}))
        await asyncio.wait_for(task, 3)
        assert stt.stream.closed and stt.stream.audio == [b"\x00\x01" * 160]
        assert stack.store.active_count(a_id) == 0 and stack.store._sessions == {} and stack.manager.usage == {}
        ours = " ".join(r.getMessage() for r in caplog.records if r.name.startswith("app"))
        assert CUSTOMER_WORDS not in ours and "We open at eight" not in ours  # no transcripts in our logs
        assert "voice call ended" in ours
    finally:
        await a.aclose(), await b.aclose()


async def test_barge_in_oversize_frames_and_malformed_controls(env):
    a, a_id, b, _, factory = await two(env)
    try:
        stt = FakeSTT([final("first question")])
        rounds = [[TextDelta(text="A long answer. "), done()], [TextDelta(text="Second answer."), done()]]
        stack = enable(env, stt, rounds)
        stack.manager._tts.slow = True  # the first reply is still "speaking" when the customer talks again
        ws, task = await call(env, a.cookies.get(env[2].session_cookie_name))
        await settle(ws, lambda: "ready" in ws.types())
        ws.client_sends(text="not json"); ws.client_sends(text="[1]")
        ws.client_sends(data=b"x" * 40_000)  # oversize: dropped
        ws.client_sends(data=b"\x01\x02")
        await settle(ws, lambda: stt.stream and len(stt.stream.audio) == 1)
        assert stt.stream.audio == [b"\x01\x02"]
        await settle(ws, lambda: ws.types().count("state") >= 2)
        stt.stream.q.put_nowait(TranscriptEvent(text="wait", is_final=False))
        await settle(ws, lambda: "interrupted" in ws.types())
        ws.hang_up()
        await asyncio.wait_for(task, 3)
        assert stack.store.active_count(a_id) == 0
    finally:
        await a.aclose(), await b.aclose()


async def test_speech_failure_mid_call_hands_over_and_ends(env):
    a, a_id, b, _, factory = await two(env)
    try:
        stt = FakeSTT([ProviderError("elevenlabs", "stream_error", "x", recoverable=False)])
        stack = enable(env, stt)
        ws, task = await call(env, a.cookies.get(env[2].session_cookie_name))
        await settle(ws, lambda: "ready" in ws.types())
        ws.client_sends(data=b"\x00\x00")
        await asyncio.wait_for(task, 3)
        assert "handover" in ws.types() and any("connect you to a team member" in m.get("text", "") for m in ws.json)
        assert stack.store.active_count(a_id) == 0
    finally:
        await a.aclose(), await b.aclose()


async def test_agents_and_limits_are_tenant_and_business_scoped(env):
    a, a_id, b, b_id, factory = await two(env)
    try:
        async with factory() as db:
            theirs = Agent(business_id=b_id, name="Beta bot", config={"voice_id": "b-voice"})
            mine = Agent(business_id=a_id, name="Alpha bot", config={"voice_id": "a-voice"})
            db.add_all([theirs, mine]); await db.commit()
        cookie = a.cookies.get(env[2].session_cookie_name)
        stack = enable(env, FakeSTT(), voice="default-voice", voice_max_concurrent_sessions_per_business=1)
        ws = FakeWS(env[0], cookie=cookie); await voice_test_call(ws, theirs.id)
        assert ws.closed == 1008 and not ws.accepted  # another business's agent looks like a missing one
        ws1, t1 = await call(env, cookie, query_agent=mine.id)
        await settle(ws1, lambda: "ready" in ws1.types())
        assert [s.voice_id for s in stack.store._sessions.values()] == ["a-voice"]
        ws2 = FakeWS(env[0], cookie=cookie); await voice_test_call(ws2, None)
        assert ws2.json == [{"type": "error", "code": "too_many_calls"}]
        ws1.hang_up(); await asyncio.wait_for(t1, 3)
    finally:
        await a.aclose(), await b.aclose()


async def test_status_endpoint_names_what_is_missing_without_values(env):
    a, a_id, b, _, factory = await two(env)
    try:
        body = (await a.get("/api/v1/voice/status")).json()
        assert body["available"] is False and "VOICE_LIVE_ENABLED" in body["missing"] and "OPENAI_API_KEY" in body["missing"]
        await add_user(factory, a_id, "Reader", ["cases:read"], "r@a.test")
        r = await login(env, "r@a.test")
        assert (await r.get("/api/v1/voice/status")).status_code == 403
        await r.aclose()
    finally:
        await a.aclose(), await b.aclose()


def test_stack_is_built_only_when_opted_in_with_both_keys():
    assert missing_for_live_voice(Settings(_env_file=None)) == ["VOICE_LIVE_ENABLED", "OPENAI_API_KEY", "ELEVENLABS_API_KEY"]
    assert build_voice_stack(Settings(_env_file=None, openai_api_key="k", elevenlabs_api_key="k"), None) is None  # not opted in
    on = Settings(_env_file=None, voice_live_enabled=True, openai_api_key="k", elevenlabs_api_key="k", voice_disabled_providers=["openai"])
    stack = build_voice_stack(on, None)
    assert stack is not None and not stack.controls.is_enabled("openai") and stack.controls.is_enabled("elevenlabs")


class Probe:
    def __init__(self, result): self.result = result
    async def health_check(self):
        if isinstance(self.result, Exception):
            raise self.result
        if self.result == "slow":
            await asyncio.sleep(60)
        return self.result


async def test_provider_check_reports_each_provider_without_leaking_errors(env):
    a, a_id, b, _, factory = await two(env)
    try:
        r = await a.post("/api/v1/voice/provider-check")
        assert r.json() == {"checked": False, "missing": ["VOICE_LIVE_ENABLED", "OPENAI_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID"], "results": {}}
        stack = enable(env, voice_live_enabled=True, openai_api_key="k", elevenlabs_api_key="k")
        stack.reasoning, stack.tts = Probe(True), Probe(RuntimeError("sk-SECRET leaked in message"))
        stack.stt = Probe(False)
        r = await a.post("/api/v1/voice/provider-check")
        body = r.json()
        assert body["checked"] is True and body["all_ok"] is False
        assert body["results"]["openai_reasoning"]["ok"] is True
        assert body["results"]["elevenlabs_speech"] == {"ok": False, "milliseconds": body["results"]["elevenlabs_speech"]["milliseconds"], "reason": "error"}
        assert body["results"]["elevenlabs_recognition"]["reason"] == "not_reachable_or_not_configured"
        assert "SECRET" not in r.text
        stack.stt = Probe(True); stack.tts = Probe(True)
        assert (await a.post("/api/v1/voice/provider-check")).json()["all_ok"] is True
        from app.database.models import AuditEvent
        from sqlalchemy import select
        async with factory() as db:
            ev = (await db.execute(select(AuditEvent).where(AuditEvent.action == "voice.provider_check"))).scalars().all()
        assert len(ev) == 2 and all(e.business_id == a_id for e in ev) and "SECRET" not in str([e.detail for e in ev])
        await add_user(factory, a_id, "Reader", ["cases:read"], "r@a.test")
        rd = await login(env, "r@a.test")
        assert (await rd.post("/api/v1/voice/provider-check")).status_code == 403
        await rd.aclose()
    finally:
        await a.aclose(); await b.aclose()
