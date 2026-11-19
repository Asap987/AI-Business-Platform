from decimal import Decimal

from app.core.config import Settings


def make(**env) -> Settings:
    # _env_file=None keeps a developer's local .env out of the test.
    return Settings(_env_file=None, **env)


def test_defaults_are_safe():
    s = make()
    assert s.voice_store_audio is False  # no raw audio kept by default
    assert s.voice_require_recording_consent is True
    assert s.run_live_provider_tests is False  # paid tests are opt-in
    assert s.openai_api_key is None and s.elevenlabs_api_key is None


def test_models_come_from_config_not_code():
    s = make(openai_reasoning_model="some-other-model", elevenlabs_tts_model="eleven_v3")
    assert s.openai_reasoning_model == "some-other-model"
    assert s.elevenlabs_tts_model == "eleven_v3"


def test_secrets_never_appear_in_repr_or_dump():
    s = make(openai_api_key="sk-secret-123", elevenlabs_api_key="xi-secret-456")
    text = repr(s) + str(s) + str(s.model_dump())
    assert "sk-secret-123" not in text
    assert "xi-secret-456" not in text
    assert s.openai_api_key.get_secret_value() == "sk-secret-123"


def test_no_default_prices():
    p = make().voice_pricing
    assert p.elevenlabs_stt_usd_per_hour is None
    assert p.elevenlabs_tts_usd_per_1k_chars is None
    assert p.openai_models == {}


def test_pricing_loads_from_json_env(monkeypatch):
    monkeypatch.setenv(
        "VOICE_PRICING",
        '{"as_of":"2026-11-19","elevenlabs_tts_usd_per_1k_chars":"0.05",'
        '"openai_models":{"m1":{"input_usd_per_mtok":"1","output_usd_per_mtok":"5"}}}',
    )
    p = Settings(_env_file=None).voice_pricing
    assert p.elevenlabs_tts_usd_per_1k_chars == Decimal("0.05")
    assert p.openai_models["m1"].output_usd_per_mtok == Decimal("5")
