"""
Usage tracking and cost estimation.

No provider price is hardcoded. Rates come from Settings.voice_pricing, which
an operator fills from the providers' current price lists. Every estimate
carries the rates it used (and the date they were taken from) so past numbers
stay explainable after prices change, and a missing rate yields an explicit
gap rather than a made-up figure.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.config import PricingTable
from app.services.voice.interfaces.reasoning import ReasoningUsage

_SIX_PLACES = Decimal("0.000001")


class UsageRecord(BaseModel):
    business_id: UUID
    session_id: UUID
    stt_seconds: float = 0.0
    tts_characters: int = 0
    llm: list[ReasoningUsage] = Field(default_factory=list)
    provider_errors: int = 0
    retries: int = 0  # speech-provider connection retries
    response_latencies_ms: list[int] = Field(default_factory=list)  # customer message to first audio, per turn

    def add_llm(self, usage: ReasoningUsage) -> None:
        self.llm.append(usage)


class CostLine(BaseModel):
    item: str
    quantity: Decimal
    unit: str
    rate_usd: Decimal | None
    cost_usd: Decimal | None


class CostEstimate(BaseModel):
    lines: list[CostLine]
    # Sum of the lines that could be priced. Only the whole cost if complete is True.
    total_usd: Decimal
    complete: bool
    missing_rates: list[str]
    pricing_as_of: date | None
    pricing_source_note: str


def _line(item: str, quantity: Decimal, unit: str, rate: Decimal | None, divisor: Decimal) -> CostLine:
    cost = None if rate is None else (quantity / divisor * rate).quantize(_SIX_PLACES)
    return CostLine(item=item, quantity=quantity, unit=unit, rate_usd=rate, cost_usd=cost)


def estimate_cost(usage: UsageRecord, pricing: PricingTable) -> CostEstimate:
    lines: list[CostLine] = []

    lines.append(
        _line(
            "elevenlabs_stt",
            Decimal(str(usage.stt_seconds)),
            "seconds (rate per hour)",
            pricing.elevenlabs_stt_usd_per_hour,
            Decimal(3600),
        )
    )
    lines.append(
        _line(
            "elevenlabs_tts",
            Decimal(usage.tts_characters),
            "characters (rate per 1k)",
            pricing.elevenlabs_tts_usd_per_1k_chars,
            Decimal(1000),
        )
    )

    # Aggregate tokens per model so each model is priced at its own rate.
    per_model: dict[str, tuple[int, int]] = {}
    for u in usage.llm:
        inp, out = per_model.get(u.model, (0, 0))
        per_model[u.model] = (inp + u.input_tokens, out + u.output_tokens)

    for model, (inp, out) in sorted(per_model.items()):
        rate = pricing.openai_models.get(model)
        lines.append(
            _line(f"openai:{model}:input", Decimal(inp), "tokens (rate per 1M)",
                  rate.input_usd_per_mtok if rate else None, Decimal(1_000_000))
        )
        lines.append(
            _line(f"openai:{model}:output", Decimal(out), "tokens (rate per 1M)",
                  rate.output_usd_per_mtok if rate else None, Decimal(1_000_000))
        )

    # A line with zero quantity needs no rate, so it is not a "missing rate".
    missing = [ln.item for ln in lines if ln.rate_usd is None and ln.quantity > 0]
    total = sum((ln.cost_usd for ln in lines if ln.cost_usd is not None), Decimal(0))

    return CostEstimate(
        lines=lines,
        total_usd=total.quantize(_SIX_PLACES),
        complete=not missing,
        missing_rates=missing,
        pricing_as_of=pricing.as_of,
        pricing_source_note=pricing.source_note,
    )
