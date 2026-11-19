"""
Language registry and language decisions for voice calls.

Provider support is recorded from the providers' published documentation
(checked 2026-11-19) and is deliberately conservative:

* English and French: documented for ElevenLabs Scribe (STT) and Flash v2.5 (TTS).
* Hausa: documented for Scribe (STT, "good" accuracy tier) but speech output only
  on Eleven v3, which is slower and not a low-latency model.
* Twi, Ewe, Ga: not documented for ElevenLabs STT or TTS. They are registered so
  the AI can recognise a request for them and respond honestly, but they can
  never be enabled until a provider supports them and tests pass.

Nothing is "tested" yet: every documented language starts as NOT_TESTED, which
makes it usable only as a prototype language outside production. Flip a
language to PASSED only after recorded tests with real Ghanaian speakers.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.core.config import Settings


class ProviderSupport(str, Enum):
    DOCUMENTED = "documented"  # provider docs list the language
    NONE = "none"  # provider docs do not list it


class TestingStatus(str, Enum):
    __test__ = False  # not a pytest class

    NOT_TESTED = "not_tested"
    PASSED = "passed"
    FAILED = "failed"


class Availability(str, Enum):
    ENABLED = "enabled"  # documented AND tested: production-ready
    PROTOTYPE = "prototype"  # documented, untested: non-production only
    UNSUPPORTED = "unsupported"  # a provider cannot do it
    DISABLED = "disabled"  # tests failed


class FallbackBehavior(str, Enum):
    ASK_CLARIFICATION = "ask_clarification"
    OFFER_ALTERNATIVES = "offer_alternatives"
    ESCALATE_TO_HUMAN = "escalate_to_human"


class LanguageConfig(BaseModel):
    name: str
    code: str  # canonical code used inside the platform (ISO 639-1 where one exists)
    # Codes providers use for this language; matched case-insensitively.
    aliases: list[str] = Field(default_factory=list)
    stt_support: ProviderSupport
    tts_support: ProviderSupport
    # "default" -> settings.elevenlabs_tts_model, "expressive" -> ..._expressive_model
    tts_model_tier: str = "default"
    # Approved ElevenLabs voice IDs for this language. Filled in by operators;
    # none are invented here.
    voice_ids: list[str] = Field(default_factory=list)
    testing_status: TestingStatus = TestingStatus.NOT_TESTED
    fallback: FallbackBehavior = FallbackBehavior.OFFER_ALTERNATIVES
    notes: str = ""


DEFAULT_LANGUAGES: list[LanguageConfig] = [
    LanguageConfig(
        name="English",
        code="en",
        aliases=["eng"],
        stt_support=ProviderSupport.DOCUMENTED,
        tts_support=ProviderSupport.DOCUMENTED,
        notes="Scribe excellent tier (<=5% WER). Needs testing with Ghanaian-accented English.",
    ),
    LanguageConfig(
        name="French",
        code="fr",
        aliases=["fra"],
        stt_support=ProviderSupport.DOCUMENTED,
        tts_support=ProviderSupport.DOCUMENTED,
        notes="Scribe excellent tier (<=5% WER).",
    ),
    LanguageConfig(
        name="Hausa",
        code="ha",
        aliases=["hau"],
        stt_support=ProviderSupport.DOCUMENTED,
        tts_support=ProviderSupport.DOCUMENTED,
        tts_model_tier="expressive",
        notes=(
            "Scribe 'good' tier only (>10% to <=20% WER). Speech output requires Eleven v3 "
            "(slower, 5,000-character limit). Expect higher latency than English/French."
        ),
    ),
    LanguageConfig(
        name="Twi",
        code="tw",
        aliases=["twi", "ak", "aka", "akan"],
        stt_support=ProviderSupport.NONE,
        tts_support=ProviderSupport.NONE,
        fallback=FallbackBehavior.ESCALATE_TO_HUMAN,
        notes="Not listed for ElevenLabs STT or TTS. Cannot be enabled without another provider.",
    ),
    LanguageConfig(
        name="Ewe",
        code="ee",
        aliases=["ewe"],
        stt_support=ProviderSupport.NONE,
        tts_support=ProviderSupport.NONE,
        fallback=FallbackBehavior.ESCALATE_TO_HUMAN,
        notes="Not listed for ElevenLabs STT or TTS.",
    ),
    LanguageConfig(
        name="Ga",
        code="gaa",
        aliases=["gaa"],
        stt_support=ProviderSupport.NONE,
        tts_support=ProviderSupport.NONE,
        fallback=FallbackBehavior.ESCALATE_TO_HUMAN,
        notes="Not listed for ElevenLabs STT or TTS.",
    ),
]


class LanguageAction(str, Enum):
    CONTINUE = "continue"
    SWITCH = "switch"
    ASK_CLARIFICATION = "ask_clarification"
    OFFER_ALTERNATIVES = "offer_alternatives"
    ESCALATE = "escalate"


class LanguageDecision(BaseModel):
    action: LanguageAction
    language_code: str  # the language the AI should speak next
    unsupported_attempts: int
    alternatives: list[str] = Field(default_factory=list)  # names of usable languages
    # Instruction for the reasoning engine. The AI never silently translates
    # uncertain speech or presents a guess as confirmed information.
    guidance: str = ""


class LanguageManager:
    def __init__(
        self,
        settings: Settings,
        languages: list[LanguageConfig] | None = None,
        max_unsupported_attempts: int = 2,
    ) -> None:
        self._settings = settings
        self._max_attempts = max_unsupported_attempts
        self._by_code: dict[str, LanguageConfig] = {}
        self._lookup: dict[str, LanguageConfig] = {}
        # Copy, so changing one manager's languages (e.g. marking one as tested)
        # can never leak into the shared defaults or another manager.
        for source in languages if languages is not None else DEFAULT_LANGUAGES:
            lang = source.model_copy(deep=True)
            self._by_code[lang.code] = lang
            for key in [lang.code, *lang.aliases]:
                self._lookup[key.lower()] = lang

    # ---- registry queries -------------------------------------------------
    def get(self, code: str | None) -> LanguageConfig | None:
        return self._lookup.get(code.lower()) if code else None

    def availability(self, code: str | None) -> Availability:
        lang = self.get(code)
        if lang is None:
            return Availability.UNSUPPORTED
        if lang.stt_support is ProviderSupport.NONE or lang.tts_support is ProviderSupport.NONE:
            return Availability.UNSUPPORTED
        if lang.testing_status is TestingStatus.FAILED:
            return Availability.DISABLED
        if lang.testing_status is TestingStatus.PASSED:
            return Availability.ENABLED
        return Availability.PROTOTYPE

    def is_usable(self, code: str | None) -> bool:
        state = self.availability(code)
        if state is Availability.ENABLED:
            return True
        if state is Availability.PROTOTYPE:
            return (
                self._settings.voice_allow_prototype_languages
                and self._settings.environment != "production"
            )
        return False

    def usable_languages(self) -> list[LanguageConfig]:
        return [lang for lang in self._by_code.values() if self.is_usable(lang.code)]

    def tts_model_id(self, code: str) -> str:
        lang = self.get(code)
        if lang is not None and lang.tts_model_tier == "expressive":
            return self._settings.elevenlabs_tts_expressive_model
        return self._settings.elevenlabs_tts_model

    # ---- decisions --------------------------------------------------------
    def decide(
        self,
        *,
        detected_code: str | None,
        probability: float | None,
        current_language: str,
        unsupported_attempts: int = 0,
    ) -> LanguageDecision:
        current = self.get(current_language)
        current_code = current.code if current else current_language

        # No detection information: keep going in the current language.
        if detected_code is None:
            return LanguageDecision(
                action=LanguageAction.CONTINUE,
                language_code=current_code,
                unsupported_attempts=unsupported_attempts,
            )

        # Detection present but not reliable enough to act on.
        if probability is not None and probability < self._settings.voice_min_language_probability:
            return LanguageDecision(
                action=LanguageAction.ASK_CLARIFICATION,
                language_code=current_code,
                unsupported_attempts=unsupported_attempts,
                guidance=(
                    "The language of the last utterance could not be identified reliably. "
                    "Do not guess what the customer said. Politely ask them to repeat it, "
                    "and ask which language they prefer."
                ),
            )

        detected = self.get(detected_code)
        alternatives = [lang.name for lang in self.usable_languages()]

        if not self.is_usable(detected_code):
            attempts = unsupported_attempts + 1
            name = detected.name if detected else "that language"
            if attempts >= self._max_attempts:
                return LanguageDecision(
                    action=LanguageAction.ESCALATE,
                    language_code=current_code,
                    unsupported_attempts=attempts,
                    alternatives=alternatives,
                    guidance=(
                        f"The customer keeps speaking {name}, which this service cannot understand "
                        "reliably. Do not guess or translate. Apologise, say you are connecting "
                        "them to a team member who can help, and transfer the call."
                    ),
                )
            return LanguageDecision(
                action=LanguageAction.OFFER_ALTERNATIVES,
                language_code=current_code,
                unsupported_attempts=attempts,
                alternatives=alternatives,
                guidance=(
                    f"The customer seems to be speaking {name}, which cannot be understood "
                    "reliably yet. Do not guess what they said. Say so politely in the current "
                    f"language, offer to continue in {', '.join(alternatives) or 'a supported language'}, "
                    "or offer a team member."
                ),
            )

        assert detected is not None
        if detected.code == current_code:
            return LanguageDecision(
                action=LanguageAction.CONTINUE,
                language_code=current_code,
                unsupported_attempts=0,
            )
        return LanguageDecision(
            action=LanguageAction.SWITCH,
            language_code=detected.code,
            unsupported_attempts=0,
            guidance=f"The customer switched to {detected.name}. Reply in {detected.name}.",
        )
