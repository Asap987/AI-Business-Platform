"""Callback requests. Reachable with cases:read / cases:write; every query is scoped to the caller's business, and another
business's request answers 404. The phone number is business data: it is shown here, never written to the audit log."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import Principal, get_db, require
from app.database.models import CallbackRequest
from app.services import callbacks as svc
from app.services.cases import RuleError
from app.services.telephony.context import HandoverContext

router = APIRouter(prefix="/callbacks", tags=["callbacks"])
Status = Literal["pending", "contacted", "done", "cancelled"]


class CallbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: str = Field(max_length=30)
    reason: str = Field(min_length=2, max_length=500)
    caller_name: str | None = Field(default=None, max_length=200)
    preferred_time: str | None = Field(default=None, max_length=100)
    department_id: UUID | None = None
    customer_id: UUID | None = None
    context: HandoverContext | None = None


class CallbackPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Status | None = None
    note: str | None = Field(default=None, max_length=1000)


def out(c: CallbackRequest) -> dict:
    return {"id": str(c.id), "department_id": str(c.department_id) if c.department_id else None, "customer_id": str(c.customer_id) if c.customer_id else None,
            "caller_name": c.caller_name, "phone": c.phone, "reason": c.reason, "preferred_time": c.preferred_time, "context": c.context or {},
            "source": c.source, "status": c.status, "note": c.note, "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat()}


def _rule(err: RuleError) -> HTTPException:
    return HTTPException(err.status, err.message)


@router.post("", status_code=201)
async def create(body: CallbackIn, p: Principal = Depends(require("cases:write")), db: AsyncSession = Depends(get_db)):
    try:
        row = await svc.create_callback(db, p.business_id, phone=body.phone, reason=body.reason, source="staff", actor_user_id=p.user.id,
                                        department_id=body.department_id, customer_id=body.customer_id, caller_name=body.caller_name,
                                        preferred_time=body.preferred_time, context=body.context)
    except RuleError as err:
        await db.rollback()
        raise _rule(err) from None
    await db.commit()
    return out(row)


@router.get("")
async def list_callbacks(status: Status | None = None, department_id: UUID | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                         p: Principal = Depends(require("cases:read")), db: AsyncSession = Depends(get_db)):
    where = [CallbackRequest.business_id == p.business_id]
    if status:
        where.append(CallbackRequest.status == status)
    if department_id:
        where.append(CallbackRequest.department_id == department_id)
    total = (await db.execute(select(func.count()).select_from(CallbackRequest).where(*where))).scalar_one()
    rows = (await db.execute(select(CallbackRequest).where(*where).order_by(CallbackRequest.created_at.desc(), CallbackRequest.id)
                             .limit(page_size).offset((page - 1) * page_size))).scalars().all()
    return {"items": [out(r) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.patch("/{callback_id}")
async def update(callback_id: UUID, body: CallbackPatch, p: Principal = Depends(require("cases:write")), db: AsyncSession = Depends(get_db)):
    row = await svc.get_callback(db, p.business_id, callback_id)
    if row is None:
        raise HTTPException(404, "Callback request not found")
    try:
        await svc.set_status(db, p.business_id, row, body.status or row.status, body.note if "note" in body.model_fields_set else None, p.user.id)
    except RuleError as err:
        await db.rollback()
        raise _rule(err) from None
    await db.commit()
    return out(row)
