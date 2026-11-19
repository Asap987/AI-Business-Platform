"""
Application settings, loaded from environment variables (and an optional
.env file for local development). Secrets are SecretStr so they never appear
in logs, reprs or tracebacks; call .get_secret_value() only at the point of
use inside a provider adapter.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelRate(BaseModel):
    """OpenAI text-model price, USD per million tokens."""

    input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal


class PricingTable(BaseModel):
    """
    Provider prices used ONLY for cost estimates. Nothing here is a default
    price: every rate is None/empty until an operator supplies the current
    figure from the provider's price list, so we never report a made-up cost.
    The rate and the date it was taken from are stored with each estimate.
    """

    as_of: date | None = None
    source_note: str = ""
    elevenlabs_stt_usd_per_hour: Decimal | None = None
    elevenlabs_tts_usd_per_1k_chars: Decimal | None = None
    openai_models: dict[str, ModelRate] = Field(default_factory=dict)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["development", "test", "production"] = "development"

    # ---- OpenAI (intelligence) -------------------------------------------
    openai_api_key: SecretStr | None = None
    # Model IDs are configuration, never hardcoded at call sites.
    openai_reasoning_model: str = "gpt-6.1-terra"
    openai_fast_model: str = "gpt-6-luna"  # cheap classification / summaries
    openai_request_timeout_seconds: float = 20.0
    openai_max_retries: int = 2

    # ---- ElevenLabs (ears and voice) -------------------------------------
    elevenlabs_api_key: SecretStr | None = None
    elevenlabs_stt_model: str = "scribe_v3_live"
    elevenlabs_stt_fallback_model: str = "scribe_v2_realtime"
    elevenlabs_tts_model: str = "eleven_flash_v2_5"  # low latency: English, French
    elevenlabs_tts_expressive_model: str = "eleven_v3"  # needed for Hausa; slower
    elevenlabs_request_timeout_seconds: float = 15.0
    elevenlabs_max_retries: int = 2

    # ---- Voice sessions ---------------------------------------------------
    voice_default_language: str = "en"
    voice_session_max_seconds: int = 900
    voice_silence_timeout_seconds: int = 30
    # Below this detected-language probability the AI asks for clarification
    # instead of acting on the transcript.
    voice_min_language_probability: float = Field(default=0.7, ge=0.0, le=1.0)
    # Prototype languages (documented support, not yet tested with Ghanaian
    # speakers) are usable outside production only.
    voice_allow_prototype_languages: bool = True
    voice_max_concurrent_sessions_per_business: int = Field(default=10, ge=1)
    voice_max_new_sessions_per_minute_per_business: int = Field(default=30, ge=1)

    # ---- Recording and retention (off by default) -------------------------
    voice_store_audio: bool = False
    voice_require_recording_consent: bool = True
    voice_audio_retention_days: int = Field(default=0, ge=0)
    voice_transcript_retention_days: int = Field(default=90, ge=0)

    # ---- Cost tracking ----------------------------------------------------
    voice_pricing: PricingTable = Field(default_factory=PricingTable)

    # ---- Live provider tests (cost money; explicit opt-in) ----------------
    run_live_provider_tests: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
