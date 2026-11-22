import pytest

from app.core.config import Settings
from app.services.voice.language_manager import (
    Availability,
    LanguageAction,
    LanguageManager,
    TestingStatus,
)


def manager(**env) -> LanguageManager:
    return LanguageManager(Settings(_env_file=None, **env))


def test_ghanaian_languages_without_provider_support_are_unsupported():
    m = manager()
    for code in ("tw", "ee", "gaa"):
        assert m.availability(code) is Availability.UNSUPPORTED
        assert not m.is_usable(code)


def test_documented_but_untested_languages_are_prototype_only():
    m = manager()
    for code in ("en", "fr", "ha"):
        assert m.availability(code) is Availability.PROTOTYPE
    assert m.is_usable("en")


def test_prototype_languages_are_blocked_in_production():
    m = manager(environment="production")
    assert not m.is_usable("en")  # nothing is tested yet, so nothing is live
    assert m.usable_languages() == []


def test_passed_language_is_usable_in_production():
    m = manager(environment="production")
    m.get("en").testing_status = TestingStatus.PASSED
    assert m.availability("en") is Availability.ENABLED
    assert [lang.code for lang in m.usable_languages()] == ["en"]


def test_provider_codes_resolve_case_insensitively():
    m = manager()
    assert m.get("ENG").code == "en"  # Scribe reports ISO 639-3
    assert m.get("hau").code == "ha"
    assert m.get("Akan").code == "tw"
    assert m.get("xx") is None and m.get(None) is None


def test_hausa_speech_uses_the_expressive_model_english_uses_flash():
    m = manager()
    assert m.tts_model_id("en") == "eleven_flash_v2_5"
    assert m.tts_model_id("ha") == "eleven_v3"


def test_no_voice_ids_are_invented():
    assert all(lang.voice_ids == [] for lang in manager()._by_code.values())


def test_no_detection_info_continues():
    d = manager().decide(detected_code=None, probability=None, current_language="en")
    assert d.action is LanguageAction.CONTINUE


def test_low_confidence_asks_for_clarification_and_never_switches():
    d = manager().decide(detected_code="fra", probability=0.4, current_language="en")
    assert d.action is LanguageAction.ASK_CLARIFICATION
    assert d.language_code == "en"
    assert "Do not guess" in d.guidance


def test_same_language_continues_and_resets_attempts():
    d = manager().decide(detected_code="eng", probability=0.95, current_language="en", unsupported_attempts=1)
    assert d.action is LanguageAction.CONTINUE
    assert d.unsupported_attempts == 0


def test_customer_can_switch_language_mid_call():
    d = manager().decide(detected_code="fra", probability=0.9, current_language="en")
    assert d.action is LanguageAction.SWITCH
    assert d.language_code == "fr"


def test_unsupported_language_first_time_offers_alternatives_without_switching():
    d = manager().decide(detected_code="twi", probability=0.9, current_language="en")
    assert d.action is LanguageAction.OFFER_ALTERNATIVES
    assert d.language_code == "en"
    assert d.unsupported_attempts == 1
    assert "English" in d.alternatives and "Twi" not in d.alternatives
    assert "Do not guess" in d.guidance


def test_unsupported_language_repeated_escalates_to_human():
    d = manager().decide(detected_code="ewe", probability=0.9, current_language="en", unsupported_attempts=1)
    assert d.action is LanguageAction.ESCALATE
    assert "transfer" in d.guidance


def test_unknown_language_code_is_treated_as_unsupported():
    d = manager().decide(detected_code="zzz", probability=0.9, current_language="en")
    assert d.action is LanguageAction.OFFER_ALTERNATIVES


@pytest.mark.parametrize("code", ["en", "fr", "ha"])
def test_prototype_language_not_offered_as_alternative_in_production(code):
    m = manager(environment="production")
    d = m.decide(detected_code="twi", probability=0.9, current_language=code)
    assert d.alternatives == []
