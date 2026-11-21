from __future__ import annotations

from pydantic import BaseModel, Field


class SpeechChunk(BaseModel):
    """A slice of synthesised audio, in playback order."""

    audio: bytes
    sequence: int = Field(ge=0)
    is_final: bool = False
    audio_format: str = "pcm_16000"


class VoiceSettingsOverride(BaseModel):
    """Optional per-business voice tuning (provider adapters map these)."""

    # ElevenLabs accepts 0.7 to 1.2 for speed.
    speed: float | None = Field(default=None, ge=0.7, le=1.2)
    stability: float | None = Field(default=None, ge=0.0, le=1.0)
    similarity_boost: float | None = Field(default=None, ge=0.0, le=1.0)


class TTSRequest(BaseModel):
    voice_id: str
    language_code: str
    model_id: str
    settings: VoiceSettingsOverride = Field(default_factory=VoiceSettingsOverride)
