"""
Runs one customer turn end to end: language decision -> reasoning (streamed)
-> tools -> speech (streamed) -> audio sink, with interruption (barge-in),
bounded tool rounds, and a human hand-over when something fails.

Speech starts as soon as the first sentence is written; a customer
interruption cancels reasoning and speech together. All business data and
actions go through the BusinessToolGateway. Nothing here talks to a provider
directly.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field

from app.core.config import Settings
from app.services.voice.errors import ProviderError
from app.services.voice.interfaces.business_tools import BusinessToolGateway, ToolResult
from app.services.voice.interfaces.reasoning import (
    ReasoningEngine,
    ReasoningRequest,
    TextDelta,
    ToolCallRequested,
    ToolExchange,
    TurnCompleted,
)
from app.services.voice.interfaces.text_to_speech import TextToSpeech
from app.services.voice.language_manager import LanguageAction, LanguageManager
from app.services.voice.schemas.speech_response import SpeechChunk, TTSRequest
from app.services.voice.schemas.voice_session import (
    SessionState,
    Speaker,
    ToolCallRecord,
    TranscriptTurn,
    VoiceSession,
)
from app.services.voice.usage import UsageRecord

logger = logging.getLogger(__name__)

AudioSink = Callable[[SpeechChunk], Awaitable[None]]
ESCALATION_TOOL = "escalate_to_human"
HANDOVER_MESSAGE = "I'm sorry, I'm having trouble. Let me connect you to a team member who can help."
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_MAX_CHUNK = 220


class SentenceBuffer:
    """Groups streamed text into speakable sentences."""

    def __init__(self) -> None:
        self._buf = ""

    def feed(self, text: str) -> list[str]:
        self._buf += text
        parts = _SENTENCE_END.split(self._buf)
        self._buf = parts.pop()
        out = [p.strip() for p in parts if p.strip()]
        while len(self._buf) > _MAX_CHUNK:  # a very long run with no full stop
            cut = self._buf.rfind(" ", 0, _MAX_CHUNK)
            cut = cut if cut > 0 else _MAX_CHUNK
            out.append(self._buf[:cut].strip())
            self._buf = self._buf[cut:].lstrip()
        return out

    def flush(self) -> list[str]:
        rest, self._buf = self._buf.strip(), ""
        return [rest] if rest else []


@dataclass
class TurnOutcome:
    spoken_text: str = ""
    escalated: bool = False
    interrupted: bool = False
    error_code: str | None = None


@dataclass
class _Turn:
    session: VoiceSession
    outcome: TurnOutcome = field(default_factory=TurnOutcome)
    sent_text: list[str] = field(default_factory=list)
    started: float = field(default_factory=time.monotonic)
    first_audio_logged: bool = False
    task: asyncio.Task | None = None


class ConversationManager:
    def __init__(
        self,
        settings: Settings,
        reasoning: ReasoningEngine,
        tts: TextToSpeech,
        gateway: BusinessToolGateway,
        languages: LanguageManager,
        *,
        max_tool_rounds: int = 3,
    ) -> None:
        self._settings = settings
        self._reasoning = reasoning
        self._tts = tts
        self._gateway = gateway
        self._languages = languages
        self._max_rounds = max_tool_rounds
        self._turns: dict = {}
        self.usage: dict = {}

    # ---- public API -------------------------------------------------------
    def usage_for(self, session: VoiceSession) -> UsageRecord:
        return self.usage.setdefault(
            session.session_id, UsageRecord(business_id=session.business_id, session_id=session.session_id)
        )

    async def handle_utterance(
        self,
        session: VoiceSession,
        text: str,
        sink: AudioSink,
        *,
        business_context: str,
        detected_language: str | None = None,
        language_probability: float | None = None,
    ) -> TurnOutcome:
        """Process one final customer utterance; returns when the reply has been spoken."""
        await self.interrupt(session)  # speaking over the AI always wins
        turn = _Turn(session)
        turn.task = asyncio.create_task(
            self._run(turn, text, sink, business_context, detected_language, language_probability)
        )
        self._turns[session.session_id] = turn
        try:
            return await turn.task
        except asyncio.CancelledError:
            if turn.task.cancelled():  # interrupted by barge-in, not by our own caller
                return turn.outcome
            turn.task.cancel()
            raise
        finally:
            if self._turns.get(session.session_id) is turn:
                del self._turns[session.session_id]

    async def interrupt(self, session: VoiceSession) -> bool:
        """Customer started speaking: stop reasoning and speech now. True if a reply was cut off."""
        turn = self._turns.get(session.session_id)
        if turn is None or turn.task is None or turn.task.done():
            return False
        turn.task.cancel()
        await asyncio.gather(turn.task, return_exceptions=True)
        turn.outcome.interrupted = True
        return True

    async def hand_over(self, session: VoiceSession, reason: str) -> TurnOutcome:
        """Flag the call for a person (used when something outside a turn, such as speech recognition, fails)."""
        outcome = TurnOutcome()
        await self._escalate(session, reason, outcome)
        session.state = SessionState.ESCALATING
        return outcome

    # ---- the turn ---------------------------------------------------------
    async def _run(self, turn, text, sink, business_context, detected, probability) -> TurnOutcome:
        session = turn.session
        try:
            await self._run_inner(turn, text, sink, business_context, detected, probability)
        except asyncio.CancelledError:
            turn.outcome.interrupted = True
            raise
        except ProviderError as err:
            logger.warning("Turn failed: %s/%s", err.provider, err.code)
            self.usage_for(session).provider_errors += 1
            turn.outcome.error_code = err.code
            await self._escalate(session, f"provider failure: {err.provider}/{err.code}", turn.outcome)
        finally:
            spoken = " ".join(turn.sent_text).strip()
            turn.outcome.spoken_text = spoken
            if spoken:
                session.transcript.append(
                    TranscriptTurn(
                        speaker=Speaker.AI, text=spoken, language_code=session.language_code,
                        interrupted=turn.outcome.interrupted,
                    )
                )
            if session.state is not SessionState.ENDED:
                session.state = SessionState.ESCALATING if session.escalation.requested else SessionState.LISTENING
        return turn.outcome

    async def _run_inner(self, turn, text, sink, business_context, detected, probability) -> None:
        session, outcome = turn.session, turn.outcome
        session.state = SessionState.THINKING
        session.transcript.append(TranscriptTurn(speaker=Speaker.CUSTOMER, text=text, language_code=detected))

        decision = self._languages.decide(
            detected_code=detected, probability=probability,
            current_language=session.language_code, unsupported_attempts=session.unsupported_language_attempts,
        )
        session.unsupported_language_attempts = decision.unsupported_attempts
        if decision.action is LanguageAction.SWITCH:
            session.language_code = decision.language_code
        guidance = decision.guidance or None
        tools = [] if decision.action is LanguageAction.ESCALATE else await self._gateway.list_tools(
            session.business_id, session.agent_id
        )
        if decision.action is LanguageAction.ESCALATE:
            await self._escalate(session, "unsupported language", outcome)

        allowed = {t.name for t in tools}
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def text_iter() -> AsyncIterator[str]:
            while (item := await queue.get()) is not None:
                yield item

        async def produce() -> None:
            buffer, exchanges = SentenceBuffer(), []
            try:
                for _ in range(self._max_rounds + 1):
                    request = ReasoningRequest(
                        business_id=session.business_id, session_id=session.session_id,
                        language_code=session.language_code, business_context=business_context,
                        history=session.transcript[:-1], user_text=text, tools=tools,
                        tool_exchanges=exchanges, language_guidance=guidance,
                        redact_contact_details=session.redact_contact_details,
                    )
                    pending = None
                    async for event in self._reasoning.respond_stream(request):
                        if isinstance(event, TextDelta):
                            for s in buffer.feed(event.text):
                                turn.sent_text.append(s)
                                queue.put_nowait(s)
                        elif isinstance(event, ToolCallRequested):
                            pending = event
                        elif isinstance(event, TurnCompleted):
                            self.usage_for(session).add_llm(event.usage)
                            if event.needs_human and not session.escalation.requested:
                                await self._escalate(session, "model flagged human needed", outcome)
                    for s in buffer.flush():
                        turn.sent_text.append(s)
                        queue.put_nowait(s)
                    if pending is None:
                        return
                    exchanges.append(await self._run_tool(session, pending, allowed))
                    if pending.tool_name == ESCALATION_TOOL and exchanges[-1].result.ok:
                        outcome.escalated = True
                raise ProviderError("conversation", "too_many_tool_rounds", "Too many tool steps.", recoverable=False)
            finally:
                queue.put_nowait(None)

        voice_id = session.voice_id
        if not voice_id:
            raise ProviderError("conversation", "no_voice", "No voice is configured for this session.", recoverable=False)
        tts_request = TTSRequest(
            voice_id=voice_id, language_code=session.language_code,
            model_id=self._languages.tts_model_id(session.language_code),
        )

        async def speak() -> None:
            async for chunk in self._tts.synthesize_stream(tts_request, text_iter()):
                if chunk.audio and session.state is not SessionState.SPEAKING:
                    session.state = SessionState.SPEAKING
                if chunk.audio:
                    if not turn.first_audio_logged:
                        turn.first_audio_logged = True
                        self.usage_for(session).response_latencies_ms.append(round((time.monotonic() - turn.started) * 1000))
                    await sink(chunk)

        producer = asyncio.create_task(produce())
        speaker = asyncio.create_task(speak())
        try:
            await asyncio.gather(producer, speaker)
        except BaseException:
            for t in (producer, speaker):
                t.cancel()
            await asyncio.gather(producer, speaker, return_exceptions=True)
            raise
        finally:
            self.usage_for(session).tts_characters += sum(len(s) + 1 for s in turn.sent_text)

    # ---- tools & escalation ----------------------------------------------
    async def _run_tool(self, session: VoiceSession, call: ToolCallRequested, allowed: set[str]) -> ToolExchange:
        if call.tool_name not in allowed:
            result = ToolResult(ok=False, summary="That action is not available.")
        else:
            try:
                result = await self._gateway.execute(
                    business_id=session.business_id, session_id=session.session_id,
                    tool_name=call.tool_name, arguments=call.arguments,
                )
            except Exception:
                logger.exception("Business tool %s failed", call.tool_name)
                result = ToolResult(ok=False, summary="That action failed. Do not say it was done.")
        session.tool_history.append(
            ToolCallRecord(tool_name=call.tool_name, arguments=call.arguments, ok=result.ok, result_summary=result.summary)
        )
        if call.tool_name == ESCALATION_TOOL and result.ok:
            self._mark_escalated(session, str(call.arguments.get("reason", "requested")))
        return ToolExchange(call_id=call.call_id, tool_name=call.tool_name, arguments=call.arguments, result=result)

    @staticmethod
    def _mark_escalated(session: VoiceSession, reason: str) -> None:
        from datetime import datetime, timezone

        session.escalation.requested = True
        session.escalation.reason = reason[:500]
        session.escalation.at = datetime.now(timezone.utc)

    async def _escalate(self, session: VoiceSession, reason: str, outcome: TurnOutcome) -> None:
        """Ask the gateway for a human hand-over. Safe to call twice."""
        if session.escalation.requested:
            outcome.escalated = True
            return
        try:
            result = await self._gateway.execute(
                business_id=session.business_id, session_id=session.session_id,
                tool_name=ESCALATION_TOOL, arguments={"reason": reason},
            )
        except Exception:
            logger.exception("Escalation call failed")
            result = ToolResult(ok=False, summary="Escalation failed.")
        session.tool_history.append(
            ToolCallRecord(tool_name=ESCALATION_TOOL, arguments={"reason": reason}, ok=result.ok, result_summary=result.summary)
        )
        # Even if recording failed, the call must still reach a person: flag it for the telephony layer.
        self._mark_escalated(session, reason)
        outcome.escalated = True
