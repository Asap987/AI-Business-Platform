"""Usage and cost reporting. Every figure is measured usage; money is an ESTIMATE (``cost_basis: "estimate"``), priced from
platform price records and never presented as a provider invoice.

Business endpoints need ``usage:read`` (Administrator by default) and only ever see their own business. Platform
endpoints are for the people who run KASORA: the caller's user id must be in PLATFORM_ADMIN_USER_IDS, anyone else gets
the same 404 as a route that does not exist. Platform reports show totals per business, never calls or content.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import Principal, current_principal, get_db, require
from app.database.models import Business, PriceRecord, UsageSession
from app.services import audit
from app.services.usage_store import aware, summarize, usd, valid_item

router = APIRouter(prefix="/usage", tags=["usage"])
platform = APIRouter(prefix="/platform", tags=["platform"])
MAX_DAYS = 366


def _range(start: date | None, end: date | None) -> tuple[datetime, datetime]:
    end = end or datetime.now(timezone.utc).date()
    start = start or end - timedelta(days=29)
    if start > end or (end - start).days >= MAX_DAYS:
        raise HTTPException(422, f"Choose a range of at most {MAX_DAYS} days, with the start before the end.")
    return datetime.combine(start, time.min, timezone.utc), datetime.combine(end + timedelta(days=1), time.min, timezone.utc)


def _row(r: UsageSession) -> dict:
    return {"id": str(r.id), "source": r.source, "ended_at": aware(r.ended_at).isoformat(), "conversation_id": str(r.conversation_id) if r.conversation_id else None,
            "stt_seconds": r.stt_seconds, "tts_characters": r.tts_characters, "llm_requests": r.llm_requests, "llm_usage": r.llm_usage,
            "failed_requests": r.failed_requests, "retries": r.retries, "turns": r.turns, "latency_avg_ms": r.latency_avg_ms,
            "estimated_cost_usd": usd(r.cost_micro_usd), "cost_complete": r.cost_complete, "missing_rates": r.missing_rates,
            "cost_basis": "estimate"}


@router.get("/summary")
async def my_summary(start: date | None = None, end: date | None = None, p: Principal = Depends(require("usage:read")), db: AsyncSession = Depends(get_db)):
    lo, hi = _range(start, end)
    rows = (await db.execute(select(UsageSession).where(UsageSession.business_id == p.business_id, UsageSession.ended_at >= lo, UsageSession.ended_at < hi))).scalars().all()
    return {"start": lo.date().isoformat(), "end": (hi - timedelta(days=1)).date().isoformat(), **summarize(list(rows))}


@router.get("/calls")
async def my_calls(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), p: Principal = Depends(require("usage:read")), db: AsyncSession = Depends(get_db)):
    where = UsageSession.business_id == p.business_id
    total = (await db.execute(select(func.count()).select_from(UsageSession).where(where))).scalar_one()
    rows = (await db.execute(select(UsageSession).where(where).order_by(UsageSession.ended_at.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [_row(r) for r in rows], "total": total, "page": page, "page_size": page_size, "cost_basis": "estimate"}


async def platform_admin(request: Request, p: Principal = Depends(current_principal)) -> Principal:
    if str(p.user.id) not in request.app.state.settings.platform_admin_user_ids:
        raise HTTPException(404, "Not found")
    return p


@platform.get("/usage")
async def platform_usage(month: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), p: Principal = Depends(platform_admin), db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    y, m = (int(month[:4]), int(month[5:])) if month else (now.year, now.month)
    lo = datetime(y, m, 1, tzinfo=timezone.utc)
    hi = datetime(y + (m == 12), 1 if m == 12 else m + 1, 1, tzinfo=timezone.utc)
    rows = (await db.execute(select(UsageSession, Business.name).join(Business, Business.id == UsageSession.business_id)
                             .where(UsageSession.ended_at >= lo, UsageSession.ended_at < hi))).all()
    by: dict = {}
    for r, name in rows:
        by.setdefault(r.business_id, (name, []))[1].append(r)
    out = [{"business_id": str(bid), "business_name": name, **summarize(rs)["total"]} for bid, (name, rs) in by.items()]
    out.sort(key=lambda x: x["estimated_cost_usd"], reverse=True)
    audit.record(db, p.business_id, p.user.id, "platform.usage_viewed", month=f"{y:04d}-{m:02d}")
    await db.commit()
    return {"month": f"{y:04d}-{m:02d}", "cost_basis": "estimate", "businesses": out,
            "total_estimated_cost_usd": usd(sum(r.cost_micro_usd for r, _ in rows))}


class PriceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: str = Field(max_length=120)
    rate: str = Field(max_length=20)
    effective_from: date
    source_note: str = Field(default="", max_length=300)


@platform.get("/prices")
async def list_prices(p: Principal = Depends(platform_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(PriceRecord).order_by(PriceRecord.item, PriceRecord.effective_from.desc()))).scalars().all()
    return {"items": [{"id": str(r.id), "item": r.item, "rate": r.rate, "effective_from": r.effective_from.isoformat(), "source_note": r.source_note} for r in rows]}


@platform.post("/prices", status_code=201)
async def add_price(body: PriceIn, p: Principal = Depends(platform_admin), db: AsyncSession = Depends(get_db)):
    if not valid_item(body.item):
        raise HTTPException(422, "Unknown price item.")
    try:
        rate = Decimal(body.rate)
    except InvalidOperation:
        raise HTTPException(422, "The rate must be a plain number.") from None
    if not rate.is_finite() or rate < 0 or rate > 100000:
        raise HTTPException(422, "The rate must be between 0 and 100000.")
    row = PriceRecord(item=body.item, rate=str(rate), effective_from=body.effective_from, source_note=body.source_note, created_by=p.user.id)
    db.add(row)
    audit.record(db, p.business_id, p.user.id, "platform.price_added", item=body.item, effective_from=body.effective_from.isoformat())
    await db.commit()
    return {"id": str(row.id), "item": row.item, "rate": row.rate, "effective_from": row.effective_from.isoformat()}
