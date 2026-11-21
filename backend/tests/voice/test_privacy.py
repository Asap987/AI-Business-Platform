import pytest

from app.core.config import Settings
from app.services.voice.errors import ProviderError
from app.services.voice.interfaces import ReasoningRequest
from app.services.voice.language_manager import LanguageManager
from app.services.voice.privacy import ProviderControls, redact_for_provider
from app.services.voice.providers.elevenlabs_stt import ElevenLabsSTT
from app.services.voice.providers.elevenlabs_tts import ElevenLabsTTS
from app.services.voice.providers.openai_reasoning import OpenAIReasoning
from app.services.voice.schemas.speech_response import TTSRequest
from app.services.voice.schemas.transcription import STTStreamConfig
from uuid import uuid4

KEY = "k-test"


def S(**kw):
    kw.setdefault("elevenlabs_api_key", KEY)
    kw.setdefault("openai_api_key", KEY)
    return Settings(_env_file=None, **kw)


def test_valid_card_numbers_are_removed_but_other_numbers_are_kept():
    out = redact_for_provider("my card is 4111 1111 1111 1111 and order 12345678901234")
    assert "4111" not in out and "[card number removed]" in out
    assert "12345678901234" in out  # fails the Luhn check, so it is not treated as a card


@pytest.mark.parametrize("said", ["my password is hunter2", "PIN: 4821", "the one-time code is 123 456", "cvv 987"])
def test_spoken_secrets_are_removed(said):
    out = redact_for_provider(said)
    assert "[removed]" in out
    for secret in ("hunter2", "4821", "987"):
        assert secret not in out


def test_contact_details_only_masked_when_asked():
    text = "Call me on +233 24 123 4567 or ama@example.com"
    assert redact_for_provider(text) == text
    out = redact_for_provider(text, contact_details=True)
    assert "233" not in out and "ama@example.com" not in out


def test_ordinary_text_is_untouched():
    text = "My parcel number is 5521 and it was due on Monday."
    assert redact_for_provider(text) == text


def test_reasoning_input_is_redacted_by_default_and_not_when_switched_off():
    req = ReasoningRequest(
        business_id=uuid4(), session_id=uuid4(), language_code="en", business_context="",
        history=[], user_text="card 4111111111111111 please",
    )
    on = OpenAIReasoning(S(), LanguageManager(S()), client=object())
    assert "4111" not in on.build_input(req)[-1]["content"]
    off_settings = S(voice_redact_secrets=False)
    off = OpenAIReasoning(off_settings, LanguageManager(off_settings), client=object())
    assert "4111" in off.build_input(req)[-1]["content"]


def test_zero_retention_flag_adds_enable_logging_false_to_both_urls_only_when_set():
    tts_req = TTSRequest(voice_id="v", language_code="en", model_id="m")
    assert "enable_logging" not in ElevenLabsTTS(S()).build_url(tts_req)
    assert "enable_logging=false" in ElevenLabsTTS(S(elevenlabs_enable_logging=False)).build_url(tts_req)
    stt = ElevenLabsSTT(S(elevenlabs_enable_logging=False))
    assert "enable_logging=false" in stt.build_url(STTStreamConfig(), "scribe_v3_live")
    assert "enable_logging" not in ElevenLabsSTT(S()).build_url(STTStreamConfig(), "scribe_v3_live")


async def test_a_switched_off_provider_is_blocked_before_any_connection():
    controls = ProviderControls()
    controls.disable("elevenlabs")
    controls.disable("openai")
    assert not controls.is_enabled("openai") and controls.is_enabled("other")

    calls = []

    async def connector(url, headers):
        calls.append(url)

    with pytest.raises(ProviderError) as err:
        await ElevenLabsSTT(S(), connector, controls=controls).open_stream(STTStreamConfig())
    assert err.value.code == "disabled" and not err.value.recoverable and calls == []

    tts = ElevenLabsTTS(S(), connector, controls=controls)
    with pytest.raises(ProviderError):
        async for _ in tts.synthesize_stream(TTSRequest(voice_id="v", language_code="en", model_id="m"), _none()):
            pass
    assert calls == [] and await tts.health_check() is False

    eng = OpenAIReasoning(S(), LanguageManager(S()), controls=controls)
    assert await eng.health_check() is False
    controls.enable("openai")
    assert controls.is_enabled("openai")


async def _none():
    return
    yield
