"""
ElevenLabs streaming text-to-speech adapter (stream-input WebSocket).

Protocol as read from the ElevenLabs docs (checked 2026-11-20):
``wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input`` with the
``xi-api-key`` header; first message ``{"text": " ", "voice_settings": ...}``;
text messages ``{"text": "... ", "flush": true}``; end with ``{"text": ""}``;
server sends ``{"audio": <base64>}`` and finally ``{"isFinal": true}``.

Unverified: the exact server error message shape (any message carrying an
``error`` or ``message`` key without audio is treated as an error), and the
list of valid ``output_format`` values. ``language_code`` is not sent because
per-model support is not documented. Never run against the live service.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import AsyncIterator
from urllib.parse import urlencode

from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from app.core.config import Settings
from app.services.voice.errors import ProviderError
from app.services.voice.privacy import ProviderControls
from app.services.voice.interfaces.text_to_speech import TextToSpeech
from app.services.voice.providers.elevenlabs_common import (
    PROVIDER,
    Connector,
    Socket,
    connect_with_retries,
    default_connect,
    parse_json,
)
from app.services.voice.schemas.speech_response import SpeechChunk, TTSRequest

logger = logging.getLogger(__name__)


class ElevenLabsTTS(TextToSpeech):
    def __init__(self, settings: Settings, connector: Connector | None = None, retry_backoff_seconds: float = 0.2,
        controls: ProviderControls | None = None) -> None:
        self._controls = controls
        self._settings = settings
        self._connector = connector or default_connect
        self._backoff = retry_backoff_seconds

    def _api_key(self) -> str:
        if self._controls is not None:
            self._controls.require(PROVIDER)
        key = self._settings.elevenlabs_api_key
        if key is None or not key.get_secret_value():
            raise ProviderError(PROVIDER, "not_configured", "ELEVENLABS_API_KEY is not set.", recoverable=False)
        return key.get_secret_value()

    def build_url(self, request: TTSRequest) -> str:
        base = self._settings.elevenlabs_tts_url_template.format(voice_id=request.voice_id)
        params = {
            "model_id": request.model_id,
            "output_format": self._settings.elevenlabs_tts_output_format,
            "inactivity_timeout": str(self._settings.elevenlabs_tts_inactivity_timeout_seconds),
        }
        if not self._settings.elevenlabs_enable_logging:
            params["enable_logging"] = "false"
        return f"{base}?{urlencode(params)}"

    @staticmethod
    def initial_message(request: TTSRequest) -> str:
        voice_settings = {
            k: v
            for k, v in {
                "speed": request.settings.speed,
                "stability": request.settings.stability,
                "similarity_boost": request.settings.similarity_boost,
            }.items()
            if v is not None
        }
        message: dict[str, object] = {"text": " "}
        if voice_settings:
            message["voice_settings"] = voice_settings
        return json.dumps(message)

    async def synthesize_stream(
        self, request: TTSRequest, text_chunks: AsyncIterator[str]
    ) -> AsyncIterator[SpeechChunk]:
        key = self._api_key()
        socket: Socket = await connect_with_retries(
            self._connector,
            self.build_url(request),
            key,
            timeout_seconds=self._settings.elevenlabs_request_timeout_seconds,
            max_retries=self._settings.elevenlabs_max_retries,
            backoff_seconds=self._backoff,
        )
        audio_format = self._settings.elevenlabs_tts_output_format
        sender: asyncio.Task[None] | None = None
        try:
            await socket.send(self.initial_message(request))
            sender = asyncio.create_task(self._send_text(socket, text_chunks))
            sequence = 0
            while True:
                recv = asyncio.ensure_future(socket.recv())
                waiting = {recv, sender} if not sender.done() else {recv}
                await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
                if sender.done() and sender.exception() is not None:
                    recv.cancel()
                    exc = sender.exception()
                    raise exc if isinstance(exc, ProviderError) else ProviderError(
                        PROVIDER, "send_failed", f"Could not send text ({type(exc).__name__}).", recoverable=True
                    )
                if not recv.done():
                    recv.cancel()
                    continue
                try:
                    raw = recv.result()
                except ConnectionClosedOK:
                    raise ProviderError(PROVIDER, "stream_ended", "Speech ended without a final marker.", recoverable=True)
                except ConnectionClosedError:
                    raise ProviderError(PROVIDER, "connection_lost", "The speech connection dropped.", recoverable=True)
                msg = parse_json(raw)
                if msg is None:
                    continue
                audio = msg.get("audio")
                if isinstance(audio, str) and audio:
                    try:
                        data = base64.b64decode(audio, validate=True)
                    except ValueError:
                        raise ProviderError(PROVIDER, "bad_audio", "Received undecodable audio.", recoverable=True)
                    yield SpeechChunk(audio=data, sequence=sequence, audio_format=audio_format)
                    sequence += 1
                elif msg.get("isFinal"):
                    yield SpeechChunk(audio=b"", sequence=sequence, is_final=True, audio_format=audio_format)
                    return
                elif "error" in msg or "message" in msg:
                    logger.warning("ElevenLabs TTS reported an error")
                    raise ProviderError(PROVIDER, "tts_error", "ElevenLabs reported a speech error.", recoverable=True)
        finally:
            if sender is not None and not sender.done():
                sender.cancel()
            if sender is not None:
                await asyncio.gather(sender, return_exceptions=True)
            try:
                await socket.close()
            except Exception:
                pass

    @staticmethod
    async def _send_text(socket: Socket, text_chunks: AsyncIterator[str]) -> None:
        async for chunk in text_chunks:
            if not chunk.strip():
                continue
            # Text should end with a single space; flush so each sentence is voiced now.
            await socket.send(json.dumps({"text": chunk.rstrip() + " ", "flush": True}))
        await socket.send(json.dumps({"text": ""}))

    async def health_check(self) -> bool:
        """Config check, plus a connect/disconnect when a health voice id is configured."""
        try:
            key = self._api_key()
        except ProviderError:
            return False
        voice = self._settings.elevenlabs_tts_health_voice_id
        if not voice:
            return True
        try:
            socket = await connect_with_retries(
                self._connector,
                self.build_url(TTSRequest(voice_id=voice, language_code="en", model_id=self._settings.elevenlabs_tts_model)),
                key,
                timeout_seconds=self._settings.elevenlabs_request_timeout_seconds,
                max_retries=0,
                backoff_seconds=0,
            )
            await socket.close()
            return True
        except Exception:
            return False
