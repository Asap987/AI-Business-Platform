"""Builds the live voice stack from settings. Returns None unless an administrator has opted in AND both keys exist."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.services.telephony import TransferService
from app.services.telephony.factory import build_telephony
from app.services.voice.conversation_manager import ConversationManager
from app.services.voice.database_gateway import DatabaseBusinessGateway
from app.services.voice.interfaces.reasoning import ReasoningEngine
from app.services.voice.interfaces.speech_to_text import SpeechToText
from app.services.voice.interfaces.text_to_speech import TextToSpeech
from app.services.voice.language_manager import LanguageManager
from app.services.voice.privacy import ProviderControls
from app.services.voice.providers.elevenlabs_stt import ElevenLabsSTT
from app.services.voice.providers.elevenlabs_tts import ElevenLabsTTS
from app.services.voice.providers.openai_reasoning import OpenAIReasoning
from app.services.voice.session_store import InMemorySessionStore


@dataclass
class VoiceStack:
    stt: SpeechToText
    manager: ConversationManager
    store: InMemorySessionStore
    controls: ProviderControls
    languages: LanguageManager
    # Kept so the connection check can probe each provider; optional so test stacks can omit them.
    reasoning: ReasoningEngine | None = None
    tts: TextToSpeech | None = None


def missing_for_live_voice(settings: Settings) -> list[str]:
    """Names of what still has to be configured (never values)."""
    missing = []
    if not settings.voice_live_enabled:
        missing.append("VOICE_LIVE_ENABLED")
    if settings.openai_api_key is None:
        missing.append("OPENAI_API_KEY")
    if settings.elevenlabs_api_key is None:
        missing.append("ELEVENLABS_API_KEY")
    return missing


def build_voice_stack(settings: Settings, session_factory: async_sessionmaker[AsyncSession]) -> VoiceStack | None:
    if missing_for_live_voice(settings):
        return None
    controls = ProviderControls()
    for provider in settings.voice_disabled_providers:
        controls.disable(provider)
    languages = LanguageManager(settings)
    # build_telephony returns the SIMULATOR unless live telephony is fully configured and approved; results say which.
    gateway = DatabaseBusinessGateway(session_factory, _no_customer, TransferService(build_telephony(settings)))  # callers are not identified on a browser test call
    reasoning = OpenAIReasoning(settings, languages, controls=controls)
    tts = ElevenLabsTTS(settings, controls=controls)
    manager = ConversationManager(settings, reasoning, tts, gateway, languages)
    return VoiceStack(ElevenLabsSTT(settings, controls=controls), manager, InMemorySessionStore(settings), controls, languages,
                      reasoning=reasoning, tts=tts)


async def _no_customer(business_id, session_id):
    return None
