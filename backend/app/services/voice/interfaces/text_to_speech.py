from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.services.voice.schemas.speech_response import SpeechChunk, TTSRequest


class TextToSpeech(ABC):
    """Provider-independent speech generation. ElevenLabs is the first adapter."""

    @abstractmethod
    def synthesize_stream(
        self, request: TTSRequest, text_chunks: AsyncIterator[str]
    ) -> AsyncIterator[SpeechChunk]:
        """
        Turn incoming text fragments into audio as they arrive, so the first
        sound can play before the model has finished writing the reply.

        Cancelling the consuming task (or closing the iterator) must stop
        generation promptly; this is how customer interruptions discard
        outdated speech.
        """

    @abstractmethod
    async def health_check(self) -> bool: ...
