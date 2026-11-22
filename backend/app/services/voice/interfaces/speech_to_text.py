from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.services.voice.schemas.transcription import STTStreamConfig, TranscriptEvent


class STTStream(ABC):
    """One live transcription stream (one call leg)."""

    @abstractmethod
    async def send_audio(self, chunk: bytes) -> None:
        """Feed raw audio as it arrives from the call."""

    @abstractmethod
    def events(self) -> AsyncIterator[TranscriptEvent]:
        """Partial and final transcripts, in order, until the stream closes."""

    @abstractmethod
    async def close(self) -> None:
        """Stop the stream and release the provider connection. Idempotent."""


class SpeechToText(ABC):
    """Provider-independent speech recognition. ElevenLabs Scribe is the first adapter."""

    @abstractmethod
    async def open_stream(self, config: STTStreamConfig) -> STTStream: ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Cheap availability probe used to decide on fallback or human transfer."""
