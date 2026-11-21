from __future__ import annotations

from pydantic import BaseModel, Field


class TranscriptEvent(BaseModel):
    """One piece of recognised speech from any speech-to-text provider."""

    text: str
    # Partial results may still change; only final ones are acted on.
    is_final: bool
    # Provider's language code as reported (e.g. "eng"); normalise via LanguageManager.
    language_code: str | None = None
    language_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    start_seconds: float | None = None
    end_seconds: float | None = None


class STTStreamConfig(BaseModel):
    """Per-stream options handed to a speech-to-text adapter."""

    language_hint: str | None = None
    sample_rate_hz: int = 16000
    audio_encoding: str = "pcm_s16le"
    # Business-specific words (product names, places) to bias recognition.
    keyterms: list[str] = Field(default_factory=list)
