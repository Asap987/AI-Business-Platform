"""
Runs one live call: customer audio in, speech recognition, the conversation manager, audio out.

Independent of how audio arrives (browser WebSocket today, telephony later): the caller supplies
two small async callbacks and feeds audio with ``feed_audio``. Nothing here is persisted and
no transcript text is logged; the transcript lives only in the in-memory session.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.services.voice.conversation_manager import HANDOVER_MESSAGE, ConversationManager
from app.services.voice.errors import ProviderError
from app.services.voice.interfaces.speech_to_text import STTStream
from app.services.voice.schemas.speech_response import SpeechChunk
from app.services.voice.schemas.voice_session import SessionState, VoiceSession
from app.services.voice.session_store import InMemorySessionStore

logger = logging.getLogger(__name__)

SendJson = Callable[[dict[str, Any]], Awaitable[None]]
SendAudio = Callable[[bytes], Awaitable[None]]
MAX_FRAME_BYTES = 32_768


class CallRunner:
    def __init__(
        self,
        *,
        session: VoiceSession,
        stt: STTStream,
        manager: ConversationManager,
        store: InMemorySessionStore,
        send_json: SendJson,
        send_audio: SendAudio,
        business_context: str,
        watchdog_seconds: float = 2.0,
    ) -> None:
        self._s, self._stt, self._manager, self._store = session, stt, manager, store
        self._send_json, self._send_audio = send_json, send_audio
        self._context = business_context
        self._watchdog = watchdog_seconds
        self._turns: set[asyncio.Task] = set()

    async def feed_audio(self, chunk: bytes) -> None:
        if not chunk or len(chunk) > MAX_FRAME_BYTES or self._s.state is SessionState.ENDED:
            return
        try:
            await self._stt.send_audio(chunk)
        except ProviderError as err:
            await self._hand_over(f"speech recognition: {err.code}")

    async def run(self) -> None:
        """Returns when the call ends: by hang-up (``stop``), a timeout, or a hand-over."""
        self._s.state = SessionState.LISTENING
        await self._send_json({"type": "state", "state": self._s.state.value})
        watchdog = asyncio.create_task(self._watch())
        try:
            async for event in self._stt.events():
                if self._s.state is SessionState.ENDED:
                    break
                self._store.touch(self._s)
                if not event.text.strip():
                    continue
                if await self._manager.interrupt(self._s):  # the customer spoke over the assistant
                    await self._send_json({"type": "interrupted"})
                if event.is_final:
                    task = asyncio.create_task(self._reply(event.text.strip(), event.language_code, event.language_probability))
                    self._turns.add(task)
                    task.add_done_callback(self._turns.discard)
        except ProviderError as err:
            await self._hand_over(f"speech recognition: {err.code}")
        finally:
            watchdog.cancel()
            await self.stop()

    async def stop(self) -> None:
        for task in list(self._turns):
            task.cancel()
        await asyncio.gather(*self._turns, return_exceptions=True)
        self._store.end(self._s)
        try:
            await self._stt.close()
        except Exception:
            logger.warning("Closing the speech stream failed")

    # ---- internals --------------------------------------------------------
    async def _reply(self, text: str, language: str | None, probability: float | None) -> None:
        await self._send_json({"type": "transcript", "speaker": "customer", "text": text})
        await self._send_json({"type": "state", "state": SessionState.THINKING.value})

        async def sink(chunk: SpeechChunk) -> None:
            await self._send_audio(chunk.audio)

        try:
            outcome = await self._manager.handle_utterance(
                self._s, text, sink, business_context=self._context,
                detected_language=language, language_probability=probability,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # never let one failed turn kill the call silently
            logger.warning("Turn failed (%s)", type(exc).__name__)
            await self._hand_over("unexpected error")
            return
        if outcome.spoken_text:
            await self._send_json({"type": "transcript", "speaker": "assistant", "text": outcome.spoken_text,
                                   "interrupted": outcome.interrupted})
        if outcome.escalated or self._s.escalation.requested:
            await self._send_json({"type": "handover"})
        if self._s.state is not SessionState.ENDED:
            await self._send_json({"type": "state", "state": self._s.state.value})

    async def _hand_over(self, reason: str) -> None:
        """Something outside a turn failed: tell the customer in text and flag the call for a person."""
        if not self._s.escalation.requested:
            await self._manager.hand_over(self._s, reason)
            await self._send_json({"type": "transcript", "speaker": "assistant", "text": HANDOVER_MESSAGE, "interrupted": False})
        await self._send_json({"type": "handover"})
        self._store.end(self._s)

    async def _watch(self) -> None:
        while self._s.state is not SessionState.ENDED:
            await asyncio.sleep(self._watchdog)
            self._store.sweep()
        await self._stt.close()  # ends the event stream so run() returns
