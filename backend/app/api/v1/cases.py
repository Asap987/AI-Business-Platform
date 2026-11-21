from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.customers import like_escape
from app.api.v1.deps import Principal, get_db, require
from app.database.models import Case, CaseEvent, Customer
from app.services.cases import Actor, RuleError, create_case, get_case, update_case

router = APIRouter(prefix="/cases", tags=["cases"])

Status = Literal["open", "in_progress", "waiting_customer", "waiting_department", "resolved", "closed"]
Priority = Literal["low", "medium", "high", "urgent"]


class CaseIn(BaseModel):
    customer_id: UUID
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    priority: Priority = "medium"
    department_id: UUID | None = None
    conversation_id: UUID | None = None


class CasePatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    priority: Priority | None = None
    status: Status | None = None
    department_id: UUID | None = None
    assigned_employee_id: UUID | None = None
    resolution_notes: str | None = Field(default=None, max_length=5000)


def out(c: Case, customer_name: str | None = None) -> dict:
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return {
        "id": str(c.id), "customer_id": str(c.customer_id), "customer_name": customer_name, "title": c.title,
        "description": c.description, "priority": c.priority, "status": c.status,
        "department_id": str(c.department_id) if c.department_id else None,
        "assigned_employee_id": str(c.assigned_employee_id) if c.assigned_employee_id else None,
        "conversation_id": str(c.conversation_id) if c.conversation_id else None,
        "resolution_notes": c.resolution_notes, "opened_at": iso(c.opened_at), "resolved_at": iso(c.resolved_at),
        "updated_at": iso(c.updated_at),
    }


def _raise(err: RuleError):
    raise HTTPException(err.status, err.message)


@router.post("", status_code=201)
async def create(body: CaseIn, p: Principal = Depends(require("cases:write")), db: AsyncSession = Depends(get_db)):
    try:
        case = await create_case(db, p.business_id, Actor("user", p.user.id), **body.model_dump())
    except RuleError as err:
        _raise(err)
    await db.commit()
    return out(case)


@router.get("")
async def list_cases(
    status: Status | None = None, priority: Priority | None = None, department_id: UUID | None = None,
    assigned_employee_id: UUID | None = None, customer_id: UUID | None = None,
    q: str | None = Query(None, max_length=100), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    p: Principal = Depends(require("cases:read")), db: AsyncSession = Depends(get_db),
):
    where = [Case.business_id == p.business_id]
    for column, value in ((Case.status, status), (Case.priority, priority), (Case.department_id, department_id),
                          (Case.assigned_employee_id, assigned_employee_id), (Case.customer_id, customer_id)):
        if value is not None:
            where.append(column == value)
    if q and q.strip():
        pat = f"%{like_escape(q.strip().lower())}%"
        where.append(or_(func.lower(Case.title).like(pat, escape="\\"), func.lower(Case.description).like(pat, escape="\\")))
    total = (await db.execute(select(func.count()).select_from(Case).where(*where))).scalar_one()
    rows = (await db.execute(
        select(Case, Customer.full_name)
        .join(Customer, (Customer.id == Case.customer_id) & (Customer.business_id == p.business_id))
        .where(*where).order_by(Case.opened_at.desc(), Case.id).limit(page_size).offset((page - 1) * page_size)
    )).all()
    return {"items": [out(c, name) for c, name in rows], "total": total, "page": page, "page_size": page_size}


async def _owned(db, p, case_id):
    case = await get_case(db, p.business_id, case_id)
    if case is None:
        raise HTTPException(404, "Case not found")  # same answer for "missing" and "another business's"
    return case


@router.get("/{case_id}")
async def read(case_id: UUID, p: Principal = Depends(require("cases:read")), db: AsyncSession = Depends(get_db)):
    case = await _owned(db, p, case_id)
    customer = (await db.execute(select(Customer.full_name).where(Customer.id == case.customer_id, Customer.business_id == p.business_id))).scalar_one_or_none()
    return out(case, customer)


@router.patch("/{case_id}")
async def update(case_id: UUID, body: CasePatch, p: Principal = Depends(require("cases:write")), db: AsyncSession = Depends(get_db)):
    case = await _owned(db, p, case_id)
    changes = {f: getattr(body, f) for f in body.model_fields_set}
    for required in ("title", "priority", "status"):  # these cannot be cleared
        if required in changes and changes[required] is None:
            raise HTTPException(422, f"{required} cannot be empty")
    try:
        await update_case(db, p.business_id, Actor("user", p.user.id), case, changes)
    except RuleError as err:
        await db.rollback()
        _raise(err)
    await db.commit()
    return out(case)


@router.get("/{case_id}/events")
async def events(case_id: UUID, p: Principal = Depends(require("cases:read")), db: AsyncSession = Depends(get_db)):
    case = await _owned(db, p, case_id)
    rows = (await db.execute(select(CaseEvent).where(CaseEvent.case_id == case.id, CaseEvent.business_id == p.business_id)
                             .order_by(CaseEvent.created_at, CaseEvent.id))).scalars().all()
    return {"items": [{"id": str(e.id), "kind": e.kind, "actor_kind": e.actor_kind,
                       "actor_user_id": str(e.actor_user_id) if e.actor_user_id else None,
                       "detail": e.detail, "created_at": e.created_at.isoformat()} for e in rows]}
