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

from pydantic import AliasChoices, BaseModel, Field, SecretStr
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
        populate_by_name=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    # SQLAlchemy async URL, e.g. postgresql+asyncpg://user:pass@host/db (sqlite+aiosqlite:// is for tests only).
    database_url: SecretStr | None = None
    # Exact browser origins allowed to call the API with cookies (never "*").
    cors_origins: list[str] = ["http://localhost:3000"]
    session_cookie_name: str = "session"
    session_ttl_hours: int = Field(default=168, ge=1)
    auth_rate_limit_attempts: int = Field(default=10, ge=1)
    auth_rate_limit_window_seconds: int = Field(default=900, ge=1)

    # ---- Email (invitations, password reset, security notices) ------------
    # "off" sends nothing. "resend" needs RESEND_API_KEY and EMAIL_FROM on a domain verified in Resend.
    email_provider: Literal["off", "resend"] = "off"
    resend_api_key: SecretStr | None = None
    # Resend only sends once you have verified the sending domain with them AND set this to true. Until then nothing is sent.
    email_domain_verified: bool = False
    email_from: str | None = None  # e.g. "KASORA AI <no-reply@mail.yourdomain.com>"
    email_timeout_seconds: float = Field(default=10.0, gt=0)
    # Public address of the web app; email links are built from this, never from request headers.
    app_base_url: str = "http://localhost:3000"
    password_reset_minutes: int = Field(default=60, ge=5, le=1440)
    email_verification_hours: int = Field(default=48, ge=1, le=336)

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
    elevenlabs_stt_url: str = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
    elevenlabs_tts_url_template: str = "wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input"
    # Not confirmed against the docs' format list; override per deployment (e.g. ulaw_8000 for telephony).
    elevenlabs_tts_output_format: str = "pcm_16000"
    elevenlabs_tts_inactivity_timeout_seconds: int = Field(default=20, ge=1, le=180)
    elevenlabs_tts_health_voice_id: str | None = None
    # False sends enable_logging=false (ElevenLabs "Zero Retention Mode"). The docs say this is
    # enterprise-only and per request; they confirm TTS WebSocket coverage in general terms but do
    # not confirm the parameter on stream-input or on the realtime STT socket. Verify with the
    # account before relying on it.
    elevenlabs_enable_logging: bool = True
    # Redact card numbers and spoken passwords/PINs before text goes to the reasoning provider.
    voice_redact_secrets: bool = True
    # Also mask email addresses and phone numbers. Off by default: the assistant needs them
    # to log a case. Turn on for businesses that do not need contact details captured by voice.
    voice_redact_contact_details: bool = False
    # "vad", "manual" or "turn_prediction". Unset: turn_prediction for
    # scribe_v3_live, vad otherwise. Documented values; turn_prediction on a
    # given model still needs confirming in a live test.
    elevenlabs_stt_commit_strategy: str | None = None
    # With language detection on, the final language arrives in a message just
    # after the committed text; wait this long for it before emitting without.
    elevenlabs_stt_final_merge_wait_seconds: float = Field(default=0.3, ge=0.0)

    # ---- Voice sessions ---------------------------------------------------
    # Live voice is OFF until an administrator opts in: it calls paid providers.
    voice_live_enabled: bool = False
    voice_disabled_providers: list[str] = Field(default_factory=list)  # e.g. ["openai"] switches a provider off at startup
    # Used when an agent's config has no "voice_id". Set it as ELEVENLABS_VOICE_ID (ELEVENLABS_DEFAULT_VOICE_ID also works).
    elevenlabs_default_voice_id: str | None = Field(default=None, validation_alias=AliasChoices("elevenlabs_voice_id", "elevenlabs_default_voice_id"))
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
