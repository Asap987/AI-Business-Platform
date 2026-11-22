"""
ElevenLabs realtime speech-to-text (Scribe) adapter.

Written against the Realtime API reference (checked 2026-11-19):

* URL ``wss://api.elevenlabs.io/v1/speech-to-text/realtime``; auth via the
  ``xi-api-key`` header (the key is never put in the URL).
* Client sends ``{"message_type": "input_audio_chunk", "audio_base_64": ...}``.
* Server sends ``session_started``, ``partial_transcript``,
  ``committed_transcript`` and, when timestamps or language detection are on,
  ``committed_transcript_with_timestamps`` (which carries the segment's final
  ``language_code``), plus error messages before the socket closes.
* The realtime stream has no ``language_probability`` field, so transcripts
  from this adapter carry ``language_probability=None``.

Not covered by tests against the real service: nothing here has been run
against ElevenLabs. See tests/voice/test_elevenlabs_stt.py for what is
verified (against a fake socket) and the live-test opt-in for the rest.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlencode

from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from app.core.config import Settings
from app.services.voice.errors import ProviderError
from app.services.voice.privacy import ProviderControls
from app.services.voice.interfaces.speech_to_text import SpeechToText, STTStream
from app.services.voice.providers.elevenlabs_common import (
    Connector,
    Socket as _Socket,
    connect_with_retries,
    default_connect,
    parse_json as _parse_json,
)
from app.services.voice.schemas.transcription import STTStreamConfig, TranscriptEvent

logger = logging.getLogger(__name__)
PROVIDER = "elevenlabs"

_PCM_RATES = {8000, 16000, 22050, 24000, 44100, 48000}

# Error message types, normalised by _canonical() so both the camelCase names
# (scribeAuthError) and snake_case names (auth_error) in the docs are accepted.
_NON_RECOVERABLE = {
    "auth",
    "quota_exceeded",
    "unaccepted_terms",
    "invalid_request",
    "input",
    "chunk_size_exceeded",
}
_ERROR_TYPES = _NON_RECOVERABLE | {
    "error",
    "transcriber",
    "throttled",
    "rate_limited",
    "commit_throttled",
    "queue_overflow",
    "resource_exhausted",
    "session_time_limit_exceeded",
    "insufficient_audio_activity",
}




def audio_format_for(config: STTStreamConfig) -> str:
    """Map our stream config to the provider's ``audio_format`` value."""
    encoding = config.audio_encoding.lower()
    rate = config.sample_rate_hz
    if encoding in ("pcm_s16le", "pcm", "linear16") and rate in _PCM_RATES:
        return f"pcm_{rate}"
    if encoding in ("ulaw", "mulaw", "g711_ulaw") and rate == 8000:
        return "ulaw_8000"
    raise ValueError(f"Unsupported audio format for ElevenLabs STT: {encoding} at {rate} Hz")


def _canonical(message_type: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", message_type)  # "Scribe Invalid Request Error" -> Scribe_Invalid_...
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", s).lower()  # scribeAuthError -> scribe_auth_error
    s = re.sub(r"^scribe_?", "", s)
    s = re.sub(r"_?error$", "", s)
    return s or "error"


def _error_from(message_type: str, msg: dict[str, Any]) -> ProviderError | None:
    code = _canonical(message_type)
    if code not in _ERROR_TYPES and not message_type.lower().endswith("error"):
        return None
    detail = msg.get("error") or msg.get("message") or msg.get("detail") or ""
    return ProviderError(
        PROVIDER,
        code,
        str(detail)[:200] or "Speech recognition error",
        recoverable=code not in _NON_RECOVERABLE,
    )


_END = object()


class ElevenLabsSTTStream(STTStream):
    def __init__(self, socket: _Socket, *, expect_language: bool, merge_wait_seconds: float) -> None:
        self._ws = socket
        self._expect_language = expect_language
        self._merge_wait = merge_wait_seconds
        self._queue: asyncio.Queue[object] = asyncio.Queue()
        self._closed = False
        self._ended = False
        self._error: ProviderError | None = None
        self._reader = asyncio.create_task(self._read_loop())

    # ---- sending ----------------------------------------------------------
    async def send_audio(self, chunk: bytes) -> None:
        if self._closed:
            raise ProviderError(PROVIDER, "stream_closed", "The transcription stream is closed.", recoverable=False)
        if self._error is not None:
            raise self._error
        if not chunk:
            return
        payload = json.dumps(
            {"message_type": "input_audio_chunk", "audio_base_64": base64.b64encode(chunk).decode("ascii")}
        )
        try:
            await self._ws.send(payload)
        except Exception as exc:  # the socket library raises several types
            raise ProviderError(
                PROVIDER, "send_failed", f"Could not send audio ({type(exc).__name__}).", recoverable=True
            ) from exc

    # ---- receiving --------------------------------------------------------
    async def events(self) -> AsyncIterator[TranscriptEvent]:
        while True:
            item = await self._queue.get()
            if item is _END:
                if self._error is not None:
                    raise self._error
                return
            assert isinstance(item, TranscriptEvent)
            yield item

    def _emit(self, event: TranscriptEvent | None) -> None:
        if event is not None:
            self._queue.put_nowait(event)

    def _finish(self) -> None:
        if not self._ended:
            self._ended = True
            self._queue.put_nowait(_END)

    @staticmethod
    def _merge(pending: TranscriptEvent, msg: dict[str, Any]) -> TranscriptEvent:
        update: dict[str, Any] = {}
        language = msg.get("language_code")
        if isinstance(language, str) and language:
            update["language_code"] = language  # the committed value wins over partials
        words = msg.get("words")
        if isinstance(words, list) and words:
            first, last = words[0], words[-1]
            if isinstance(first, dict) and isinstance(first.get("start"), (int, float)):
                update["start_seconds"] = float(first["start"])
            if isinstance(last, dict) and isinstance(last.get("end"), (int, float)):
                update["end_seconds"] = float(last["end"])
        return pending.model_copy(update=update)

    async def _read_loop(self) -> None:
        pending: TranscriptEvent | None = None  # committed text waiting for its language
        last_language: str | None = None
        try:
            while True:
                try:
                    raw = await asyncio.wait_for(self._ws.recv(), self._merge_wait if pending else None)
                except asyncio.TimeoutError:
                    self._emit(pending)
                    pending = None
                    continue

                msg = _parse_json(raw)
                mtype = msg.get("message_type") if msg else None
                if msg is None or not isinstance(mtype, str):
                    continue

                if mtype == "committed_transcript_with_timestamps":
                    if pending is not None:
                        self._emit(self._merge(pending, msg))
                        pending = None
                    continue

                # Any other message means a waiting final won't get a companion.
                if pending is not None:
                    self._emit(pending)
                    pending = None

                if mtype == "partial_transcript":
                    text = str(msg.get("text") or "")
                    code = msg.get("language_code")
                    code = code if isinstance(code, str) and code else None
                    if code:
                        last_language = code
                    if text.strip():
                        self._emit(TranscriptEvent(text=text, is_final=False, language_code=code))
                elif mtype == "committed_transcript":
                    text = str(msg.get("text") or "").strip()
                    language, last_language = last_language, None
                    if not text:
                        continue
                    event = TranscriptEvent(text=text, is_final=True, language_code=language)
                    if self._expect_language:
                        pending = event
                    else:
                        self._emit(event)
                elif mtype in ("session_started", "warning"):
                    if mtype == "warning":
                        logger.warning("ElevenLabs STT warning received")
                else:
                    error = _error_from(mtype, msg)
                    if error is not None:
                        logger.warning("ElevenLabs STT error: %s", error.code)
                        self._error = error
                        return
                    logger.debug("Ignoring ElevenLabs STT message type %r", mtype)
        except ConnectionClosedOK:
            pass
        except ConnectionClosedError:
            self._error = ProviderError(
                PROVIDER, "connection_lost", "The speech recognition connection dropped.", recoverable=True
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error in ElevenLabs STT reader")
            self._error = ProviderError(
                PROVIDER, "reader_failed", f"Unexpected recognition failure ({type(exc).__name__}).", recoverable=True
            )
        finally:
            self._emit(pending)
            self._finish()

    # ---- closing ----------------------------------------------------------
    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._reader.cancel()
        await asyncio.gather(self._reader, return_exceptions=True)
        try:
            await self._ws.close()
        except Exception:
            pass
        self._finish()


class ElevenLabsSTT(SpeechToText):
    def __init__(
        self,
        settings: Settings,
        connector: Connector | None = None,
        retry_backoff_seconds: float = 0.2,
        controls: ProviderControls | None = None,
    ) -> None:
        self._controls = controls
        self._settings = settings
        self._connector = connector or self._default_connector
        self._backoff = retry_backoff_seconds

    # ---- configuration ----------------------------------------------------
    def _api_key(self) -> str:
        if self._controls is not None:
            self._controls.require(PROVIDER)
        key = self._settings.elevenlabs_api_key
        if key is None or not key.get_secret_value():
            raise ProviderError(PROVIDER, "not_configured", "ELEVENLABS_API_KEY is not set.", recoverable=False)
        return key.get_secret_value()

    def _commit_strategy(self, model_id: str) -> str:
        configured = self._settings.elevenlabs_stt_commit_strategy
        if configured:
            return configured
        return "turn_prediction" if model_id == "scribe_v3_live" else "vad"

    def build_url(self, config: STTStreamConfig, model_id: str) -> str:
        params: dict[str, str] = {
            "model_id": model_id,
            "audio_format": audio_format_for(config),
            "commit_strategy": self._commit_strategy(model_id),
            "include_language_detection": "true",
            "include_timestamps": "true",
        }
        if config.language_hint:
            params["language_code"] = config.language_hint
        if not self._settings.elevenlabs_enable_logging:
            params["enable_logging"] = "false"
        return f"{self._settings.elevenlabs_stt_url}?{urlencode(params)}"

    async def _default_connector(self, url: str, headers: dict[str, str]) -> _Socket:
        return await default_connect(url, headers)

    # ---- opening ----------------------------------------------------------
    async def _connect(self, url: str, key: str) -> _Socket:
        return await connect_with_retries(
            self._connector,
            url,
            key,
            timeout_seconds=self._settings.elevenlabs_request_timeout_seconds,
            max_retries=self._settings.elevenlabs_max_retries,
            backoff_seconds=self._backoff,
        )

    async def open_stream(self, config: STTStreamConfig) -> STTStream:
        key = self._api_key()
        models = [self._settings.elevenlabs_stt_model]
        fallback = self._settings.elevenlabs_stt_fallback_model
        if fallback and fallback not in models:
            models.append(fallback)

        last_error: ProviderError | None = None
        for model_id in models:
            try:
                socket = await self._connect(self.build_url(config, model_id), key)
            except ProviderError as err:
                if not err.recoverable and err.code == "auth":
                    raise  # a different model won't fix a bad key
                logger.warning("ElevenLabs STT model %s unavailable: %s", model_id, err.code)
                last_error = err
                continue
            if model_id != models[0]:
                logger.warning("Using fallback speech model %s", model_id)
            return ElevenLabsSTTStream(
                socket,
                expect_language=True,
                merge_wait_seconds=self._settings.elevenlabs_stt_final_merge_wait_seconds,
            )
        assert last_error is not None
        raise last_error

    async def health_check(self) -> bool:
        """Connect, wait for ``session_started`` (sent immediately on connect), disconnect."""
        try:
            key = self._api_key()
            url = self.build_url(STTStreamConfig(), self._settings.elevenlabs_stt_model)
            socket = await asyncio.wait_for(
                self._connector(url, {"xi-api-key": key}), self._settings.elevenlabs_request_timeout_seconds
            )
        except Exception:
            return False
        try:
            raw = await asyncio.wait_for(socket.recv(), self._settings.elevenlabs_request_timeout_seconds)
            msg = _parse_json(raw)
            return bool(msg and msg.get("message_type") == "session_started")
        except Exception:
            return False
        finally:
            try:
                await socket.close()
            except Exception:
                pass
