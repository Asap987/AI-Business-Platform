import asyncio
import logging
from uuid import uuid4

from app.core.config import Settings
from app.services.voice.business_gateway import BusinessData, InMemoryBusinessGateway
from app.services.voice.conversation_manager import ConversationManager, SentenceBuffer
from app.services.voice.errors import ProviderError
from app.services.voice.interfaces import (
    ReasoningEngine, ReasoningUsage, TextDelta, TextToSpeech, ToolCallRequested, TurnCompleted,
)
from app.services.voice.language_manager import LanguageManager
from app.services.voice.schemas.speech_response import SpeechChunk
from app.services.voice.schemas.voice_session import SessionState, Speaker
from app.services.voice.session_store import InMemorySessionStore

SECRET_WORDS = "my-very-private-sentence"


class FakeReasoning(ReasoningEngine):
    """Each call to respond_stream plays the next scripted round."""

    def __init__(self, rounds, hang_after_first=False):
        self.rounds, self.requests, self.hang = list(rounds), [], hang_after_first
        self.cancelled = False

    async def respond_stream(self, request):
        self.requests.append(request)
        script = self.rounds.pop(0)
        if isinstance(script, Exception):
            raise script
        try:
            for item in script:
                yield item
            if self.hang:
                await asyncio.sleep(30)
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    async def health_check(self):
        return True


class FakeTTS(TextToSpeech):
    def __init__(self, error=None, slow=False):
        self.texts, self.error, self.slow, self.closed, self.requests = [], error, slow, False, []

    async def synthesize_stream(self, request, text_chunks):
        self.requests.append(request)
        try:
            n = 0
            async for t in text_chunks:
                if self.error:
                    raise self.error
                self.texts.append(t)
                if self.slow:
                    await asyncio.sleep(30)
                yield SpeechChunk(audio=t.encode(), sequence=n)
                n += 1
            yield SpeechChunk(audio=b"", sequence=n, is_final=True)
        finally:
            self.closed = True

    async def health_check(self):
        return True


def done(inp=10, out=5):
    return TurnCompleted(usage=ReasoningUsage(model="m", input_tokens=inp, output_tokens=out))


def build(rounds, tts=None, **kw):
    settings = Settings(_env_file=None)
    gw = InMemoryBusinessGateway()
    biz = uuid4()
    gw.register_business(biz, BusinessData(knowledge=["We open at eight."], departments=["Delivery"]))
    store = InMemorySessionStore(settings)
    session = store.create(biz, voice_id="voice1")
    reasoning = FakeReasoning(rounds, **kw)
    tts = tts or FakeTTS()
    mgr = ConversationManager(settings, reasoning, tts, gw, LanguageManager(settings))
    audio = []

    async def sink(chunk):
        audio.append(chunk.audio)

    return mgr, session, gw, biz, reasoning, tts, audio, sink


async def say(mgr, session, sink, text="Hello", **kw):
    return await mgr.handle_utterance(session, text, sink, business_context="Acme", **kw)


def test_sentence_buffer_splits_on_sentence_ends_and_long_runs():
    b = SentenceBuffer()
    assert b.feed("Hello there. How are") == ["Hello there."]
    assert b.feed(" you? Fine") == ["How are you?"]
    assert b.flush() == ["Fine"] and b.flush() == []
    long = SentenceBuffer().feed("word " * 100)
    assert long and all(len(s) <= 220 for s in long)


async def test_reply_is_spoken_sentence_by_sentence_and_recorded():
    mgr, session, *_, tts, audio, sink = build([[TextDelta(text="Hi. We open "), TextDelta(text="at eight."), done()]])
    out = await say(mgr, session, sink)
    assert tts.texts == ["Hi.", "We open at eight."] and audio == [b"Hi.", b"We open at eight."]
    assert out.spoken_text == "Hi. We open at eight." and not out.interrupted and not out.escalated
    assert [t.speaker for t in session.transcript] == [Speaker.CUSTOMER, Speaker.AI]
    assert session.state is SessionState.LISTENING
    assert tts.requests[0].voice_id == "voice1" and tts.requests[0].model_id == "eleven_flash_v2_5"


async def test_usage_is_counted_for_reasoning_and_speech():
    mgr, session, *_, sink = build([[TextDelta(text="Hi there."), done(100, 20)]])
    await say(mgr, session, sink)
    u = mgr.usage_for(session)
    assert u.tts_characters == len("Hi there.") + 1
    assert [(x.input_tokens, x.output_tokens) for x in u.llm] == [(100, 20)]


async def test_tool_runs_through_the_gateway_and_result_goes_back_to_the_model():
    call = ToolCallRequested(call_id="c1", tool_name="create_case", arguments={"title": "Late parcel", "department": "Delivery"})
    mgr, session, gw, biz, reasoning, tts, audio, sink = build(
        [[TextDelta(text="One moment."), call, done()], [TextDelta(text="Your case is logged."), done()]]
    )
    out = await say(mgr, session, sink, "My parcel is late")
    assert len(gw.data_for(biz).cases) == 1
    second = reasoning.requests[1]
    assert second.tool_exchanges[0].result.ok and "Case created" in second.tool_exchanges[0].result.summary
    assert tts.texts == ["One moment.", "Your case is logged."]
    assert session.tool_history[0].tool_name == "create_case" and session.tool_history[0].ok
    assert not out.escalated


async def test_model_cannot_call_a_tool_that_was_not_offered():
    call = ToolCallRequested(call_id="c1", tool_name="run_sql", arguments={"q": "drop table x"})
    mgr, session, gw, biz, reasoning, *_, sink = build([[call, done()], [TextDelta(text="Sorry, I cannot do that."), done()]])
    await say(mgr, session, sink)
    assert reasoning.requests[1].tool_exchanges[0].result.ok is False
    assert session.tool_history[0].ok is False


async def test_a_crashing_tool_is_reported_as_failed_not_as_success():
    call = ToolCallRequested(call_id="c1", tool_name="search_knowledge", arguments={"query": "hours"})
    mgr, session, gw, *_, reasoning, tts, audio, sink = build([[call, done()], [TextDelta(text="I could not check."), done()]])

    async def boom(**kw):
        raise RuntimeError("db down: secret detail")

    gw.execute = boom
    await say(mgr, session, sink)
    res = reasoning.requests[1].tool_exchanges[0].result
    assert res.ok is False and "secret" not in res.summary


async def test_escalation_tool_marks_the_session_for_hand_over():
    call = ToolCallRequested(call_id="c1", tool_name="escalate_to_human", arguments={"reason": "wants a person"})
    mgr, session, gw, biz, *_, sink = build([[call, done()], [TextDelta(text="Connecting you now."), done()]])
    out = await say(mgr, session, sink, "Let me talk to someone")
    assert out.escalated and session.escalation.requested and session.state is SessionState.ESCALATING
    assert gw.data_for(biz).escalations[0][1] == "wants a person"


async def test_endless_tool_loops_are_stopped_and_handed_to_a_person():
    call = ToolCallRequested(call_id="c", tool_name="search_knowledge", arguments={"query": "hours"})
    mgr, session, gw, biz, *_, sink = build([[call, done()]] * 5)
    out = await say(mgr, session, sink)
    assert out.error_code == "too_many_tool_rounds" and out.escalated and session.escalation.requested


async def test_reasoning_failure_hands_over_to_a_person_and_counts_the_error():
    mgr, session, gw, biz, *_, sink = build([ProviderError("openai", "timeout", "slow", recoverable=True)])
    out = await say(mgr, session, sink)
    assert out.error_code == "timeout" and out.escalated
    assert mgr.usage_for(session).provider_errors == 1
    assert gw.data_for(biz).escalations and "openai/timeout" in gw.data_for(biz).escalations[0][1]


async def test_speech_failure_hands_over_too():
    mgr, session, gw, biz, *_, sink = build(
        [[TextDelta(text="Hello there."), done()]], tts=FakeTTS(error=ProviderError("elevenlabs", "connection_lost", "x", recoverable=True))
    )
    out = await say(mgr, session, sink)
    assert out.escalated and out.error_code == "connection_lost"


async def test_missing_voice_hands_over_without_calling_reasoning():
    mgr, session, gw, biz, reasoning, *_, sink = build([[TextDelta(text="Hi."), done()]])
    session.voice_id = None
    out = await say(mgr, session, sink)
    assert out.escalated and out.error_code == "no_voice"


async def test_barge_in_stops_reasoning_and_speech_and_marks_the_turn_interrupted():
    mgr, session, gw, biz, reasoning, tts, audio, sink = build(
        [[TextDelta(text="This is a long answer. "), TextDelta(text="It goes on."), done()]], tts=FakeTTS(slow=True)
    )
    task = asyncio.create_task(say(mgr, session, sink))
    await asyncio.sleep(0.05)
    assert await mgr.interrupt(session) is True
    out = await task
    assert out.interrupted and not out.error_code
    assert tts.closed
    ai = [t for t in session.transcript if t.speaker is Speaker.AI]
    assert ai and ai[0].interrupted
    assert session.state is SessionState.LISTENING
    assert await mgr.interrupt(session) is False  # nothing left to interrupt


async def test_a_new_utterance_interrupts_the_previous_reply():
    mgr, session, gw, biz, reasoning, tts, audio, sink = build(
        [[TextDelta(text="Long reply one. "), done()], [TextDelta(text="Second reply."), done()]], tts=FakeTTS(slow=True)
    )
    first = asyncio.create_task(say(mgr, session, sink, "one"))
    await asyncio.sleep(0.05)
    tts.slow = False
    second = await say(mgr, session, sink, "two")
    assert (await first).interrupted and not second.interrupted
    assert "Second reply." in second.spoken_text


async def test_unsupported_language_is_never_guessed_and_repeated_attempts_escalate():
    mgr, session, gw, biz, reasoning, *_, sink = build(
        [[TextDelta(text="Sorry, I only speak English or French."), done()], [TextDelta(text="Connecting you."), done()]]
    )
    first = await say(mgr, session, sink, "garbled", detected_language="twi", language_probability=0.95)
    assert not first.escalated and "cannot be understood" in (reasoning.requests[0].language_guidance or "")
    second = await say(mgr, session, sink, "garbled again", detected_language="twi", language_probability=0.95)
    assert second.escalated and reasoning.requests[1].tools == []  # no tools once we are handing over
    assert session.language_code == "en"  # replies stay in a supported language


async def test_low_confidence_language_asks_the_customer_to_repeat():
    mgr, session, gw, biz, reasoning, *_, sink = build([[TextDelta(text="Could you repeat that?"), done()]])
    await say(mgr, session, sink, "???", detected_language="fr", language_probability=0.2)
    assert "repeat" in reasoning.requests[0].language_guidance and session.language_code == "en"


async def test_provider_receives_tools_only_for_this_business_and_history_excludes_current_turn():
    mgr, session, gw, biz, reasoning, *_, sink = build([[TextDelta(text="Ok."), done()], [TextDelta(text="Fine."), done()]])
    await say(mgr, session, sink, "first")
    await say(mgr, session, sink, "second")
    assert {t.name for t in reasoning.requests[0].tools} == {"search_knowledge", "create_case", "escalate_to_human"}
    hist = [(t.speaker, t.text) for t in reasoning.requests[1].history]
    assert hist == [(Speaker.CUSTOMER, "first"), (Speaker.AI, "Ok.")] and reasoning.requests[1].user_text == "second"


async def test_logs_never_contain_what_the_customer_or_assistant_said(caplog):
    caplog.set_level(logging.DEBUG)
    call = ToolCallRequested(call_id="c", tool_name="run_sql", arguments={"q": SECRET_WORDS})
    mgr, session, *_, sink = build(
        [[call, done()], ProviderError("openai", "timeout", "x", recoverable=True)]
    )
    await say(mgr, session, sink, SECRET_WORDS)
    assert SECRET_WORDS not in caplog.text
