"""Saving and summarising usage. Counts are measured; money is ALWAYS an estimate priced from price records.

Price source order: platform ``price_records`` in force on the day (newest ``effective_from`` wins), then the
operator's ``VOICE_PRICING`` setting, else no rate and the cost is flagged incomplete: never a made-up figure.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import ModelRate, PricingTable, Settings
from app.database.models import PriceRecord, UsageSession
from app.services.voice.usage import UsageRecord, estimate_cost

log = logging.getLogger("app.usage")

ITEMS = ("elevenlabs_stt_usd_per_hour", "elevenlabs_tts_usd_per_1k_chars")


def valid_item(item: str) -> bool:
    if item in ITEMS:
        return True
    parts = item.split(":")
    return len(parts) == 3 and parts[0] == "openai" and bool(parts[1]) and parts[2] in ("input_usd_per_mtok", "output_usd_per_mtok")


def aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def load_pricing(db: AsyncSession, settings: Settings, on: date | None = None) -> PricingTable:
    on = on or datetime.now(timezone.utc).date()
    base = settings.voice_pricing
    stt, tts = base.elevenlabs_stt_usd_per_hour, base.elevenlabs_tts_usd_per_1k_chars
    partial: dict[str, list[Decimal | None]] = {k: [v.input_usd_per_mtok, v.output_usd_per_mtok] for k, v in base.openai_models.items()}
    rows = (await db.execute(select(PriceRecord).where(PriceRecord.effective_from <= on).order_by(PriceRecord.effective_from, PriceRecord.created_at))).scalars().all()
    latest: dict[str, PriceRecord] = {r.item: r for r in rows}  # later rows overwrite earlier ones
    notes, newest = [], base.as_of
    for item, r in latest.items():
        rate = Decimal(r.rate)
        if item == "elevenlabs_stt_usd_per_hour":
            stt = rate
        elif item == "elevenlabs_tts_usd_per_1k_chars":
            tts = rate
        else:
            _, model, kind = item.split(":")
            partial.setdefault(model, [None, None])[0 if kind == "input_usd_per_mtok" else 1] = rate
        notes.append(f"{item} from {r.effective_from}" + (f" ({r.source_note})" if r.source_note else ""))
        newest = max(newest, r.effective_from) if newest else r.effective_from
    models = {m: ModelRate(input_usd_per_mtok=i, output_usd_per_mtok=o) for m, (i, o) in partial.items() if i is not None and o is not None}
    return PricingTable(as_of=newest, source_note="; ".join(notes) or base.source_note, elevenlabs_stt_usd_per_hour=stt,
                        elevenlabs_tts_usd_per_1k_chars=tts, openai_models=models)


async def record_call(factory: async_sessionmaker[AsyncSession], settings: Settings, usage: UsageRecord, *, source: str,
                      started_at: datetime, ended_at: datetime, conversation_id: UUID | None = None) -> None:
    """Never raises: losing a usage row must not break a call that already happened."""
    try:
        async with factory() as db:
            pricing = await load_pricing(db, settings, ended_at.date())
            est = estimate_cost(usage, pricing)
            per_model: dict[str, list[int]] = defaultdict(lambda: [0, 0])
            for u in usage.llm:
                per_model[u.model][0] += u.input_tokens
                per_model[u.model][1] += u.output_tokens
            lat = usage.response_latencies_ms
            db.add(UsageSession(
                business_id=usage.business_id, session_id=usage.session_id, conversation_id=conversation_id, source=source,
                started_at=started_at, ended_at=ended_at, stt_seconds=round(usage.stt_seconds), tts_characters=usage.tts_characters,
                llm_requests=len(usage.llm), llm_usage=[{"model": m, "input_tokens": a, "output_tokens": b} for m, (a, b) in sorted(per_model.items())],
                failed_requests=usage.provider_errors, retries=usage.retries, turns=len(lat),
                latency_avg_ms=round(sum(lat) / len(lat)) if lat else None, latency_max_ms=max(lat) if lat else None,
                cost_micro_usd=int((est.total_usd * 1_000_000).to_integral_value()), cost_complete=est.complete, missing_rates=est.missing_rates,
                pricing_snapshot={"as_of": str(est.pricing_as_of) if est.pricing_as_of else None, "source": est.pricing_source_note,
                                  "lines": [{"item": l.item, "quantity": str(l.quantity), "rate_usd": None if l.rate_usd is None else str(l.rate_usd)} for l in est.lines]}))
            await db.commit()
    except Exception:
        log.exception("could not save usage for a finished call")


def usd(micro: int) -> str:
    return f"{Decimal(micro) / 1_000_000:.6f}"


def summarize(rows: list[UsageSession]) -> dict:
    """Totals and per-day/per-month series from measured counts. Cost fields are estimates, labelled as such."""
    def agg(rs: list[UsageSession]) -> dict:
        turns = sum(r.turns for r in rs)
        weighted = sum((r.latency_avg_ms or 0) * r.turns for r in rs)
        return {"calls": len(rs), "stt_seconds": sum(r.stt_seconds for r in rs), "tts_characters": sum(r.tts_characters for r in rs),
                "llm_requests": sum(r.llm_requests for r in rs), "failed_requests": sum(r.failed_requests for r in rs),
                "retries": sum(r.retries for r in rs), "turns": turns,
                "latency_avg_ms": round(weighted / turns) if turns else None, "latency_max_ms": max((r.latency_max_ms or 0 for r in rs), default=0) or None,
                "estimated_cost_usd": usd(sum(r.cost_micro_usd for r in rs)),
                "cost_complete": all(r.cost_complete for r in rs), "calls_missing_prices": sum(1 for r in rs if not r.cost_complete)}
    days: dict[str, list[UsageSession]] = defaultdict(list)
    months: dict[str, list[UsageSession]] = defaultdict(list)
    models: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        d = aware(r.ended_at).astimezone(timezone.utc).date()
        days[str(d)].append(r)
        months[f"{d.year:04d}-{d.month:02d}"].append(r)
        for m in r.llm_usage or []:
            models[m["model"]][0] += 1
            models[m["model"]][1] += m["input_tokens"]
            models[m["model"]][2] += m["output_tokens"]
    return {"cost_basis": "estimate", "total": agg(rows),
            "by_day": [{"date": k, **agg(v)} for k, v in sorted(days.items())],
            "by_month": [{"month": k, **agg(v)} for k, v in sorted(months.items())],
            "by_model": [{"model": k, "calls": v[0], "input_tokens": v[1], "output_tokens": v[2]} for k, v in sorted(models.items())]}
