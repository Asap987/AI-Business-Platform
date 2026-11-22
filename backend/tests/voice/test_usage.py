from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.core.config import ModelRate, PricingTable
from app.services.voice.interfaces.reasoning import ReasoningUsage
from app.services.voice.usage import UsageRecord, estimate_cost


def record(**kw) -> UsageRecord:
    return UsageRecord(business_id=uuid4(), session_id=uuid4(), **kw)


def test_without_prices_nothing_is_invented():
    est = estimate_cost(
        record(stt_seconds=60, tts_characters=500, llm=[ReasoningUsage(model="m", input_tokens=1000, output_tokens=200)]),
        PricingTable(),
    )
    assert est.total_usd == Decimal("0")
    assert est.complete is False
    assert set(est.missing_rates) == {"elevenlabs_stt", "elevenlabs_tts", "openai:m:input", "openai:m:output"}
    assert all(ln.cost_usd is None for ln in est.lines)


def test_costs_use_configured_rates_and_record_them():
    pricing = PricingTable(
        as_of=date(2026, 11, 19),
        source_note="test rates",
        elevenlabs_stt_usd_per_hour=Decimal("0.36"),
        elevenlabs_tts_usd_per_1k_chars=Decimal("0.10"),
        openai_models={"m": ModelRate(input_usd_per_mtok=Decimal("1"), output_usd_per_mtok=Decimal("5"))},
    )
    est = estimate_cost(
        record(stt_seconds=1800, tts_characters=2000, llm=[ReasoningUsage(model="m", input_tokens=2_000_000, output_tokens=1_000_000)]),
        pricing,
    )
    by_item = {ln.item: ln for ln in est.lines}
    assert by_item["elevenlabs_stt"].cost_usd == Decimal("0.180000")  # 0.5h * 0.36
    assert by_item["elevenlabs_tts"].cost_usd == Decimal("0.200000")  # 2k chars * 0.10/1k
    assert by_item["openai:m:input"].cost_usd == Decimal("2.000000")
    assert by_item["openai:m:output"].cost_usd == Decimal("5.000000")
    assert est.total_usd == Decimal("7.380000")
    assert est.complete is True
    assert est.pricing_as_of == date(2026, 11, 19) and est.pricing_source_note == "test rates"
    assert by_item["elevenlabs_stt"].rate_usd == Decimal("0.36")  # the rate used is stored


def test_zero_usage_is_not_a_missing_rate():
    est = estimate_cost(record(), PricingTable())
    assert est.complete is True and est.missing_rates == []


def test_each_model_priced_at_its_own_rate():
    pricing = PricingTable(
        openai_models={
            "cheap": ModelRate(input_usd_per_mtok=Decimal("0.1"), output_usd_per_mtok=Decimal("0.5")),
            "big": ModelRate(input_usd_per_mtok=Decimal("8"), output_usd_per_mtok=Decimal("40")),
        }
    )
    rec = record()
    rec.add_llm(ReasoningUsage(model="cheap", input_tokens=1_000_000))
    rec.add_llm(ReasoningUsage(model="big", input_tokens=1_000_000))
    rec.add_llm(ReasoningUsage(model="cheap", input_tokens=1_000_000))
    est = estimate_cost(rec, pricing)
    by_item = {ln.item: ln.cost_usd for ln in est.lines}
    assert by_item["openai:cheap:input"] == Decimal("0.200000")
    assert by_item["openai:big:input"] == Decimal("8.000000")


def test_partly_priced_estimate_is_flagged_incomplete():
    pricing = PricingTable(elevenlabs_tts_usd_per_1k_chars=Decimal("0.1"))
    est = estimate_cost(record(stt_seconds=10, tts_characters=1000), pricing)
    assert est.complete is False
    assert est.missing_rates == ["elevenlabs_stt"]
    assert est.total_usd == Decimal("0.100000")
