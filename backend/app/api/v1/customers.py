from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import Principal, get_db, require
from app.database.models import Customer
from app.services.cases import get_customer

router = APIRouter(prefix="/customers", tags=["customers"])
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def _clean(v: str | None) -> str | None:
    v = v.strip() if isinstance(v, str) else v
    return v or None


class CustomerIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=254, pattern=EMAIL_PATTERN)
    phone: str | None = Field(default=None, max_length=40)
    external_ref: str | None = Field(default=None, max_length=100)

    _strip = field_validator("full_name", "email", "phone", "external_ref", mode="before")(
        lambda v: v.strip() if isinstance(v, str) else v
    )


class CustomerPatch(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=254, pattern=EMAIL_PATTERN)
    phone: str | None = Field(default=None, max_length=40)
    external_ref: str | None = Field(default=None, max_length=100)

    _strip = field_validator("full_name", "email", "phone", "external_ref", mode="before")(
        lambda v: v.strip() if isinstance(v, str) else v
    )


def out(c: Customer) -> dict:
    return {"id": str(c.id), "full_name": c.full_name, "email": c.email, "phone": c.phone,
            "external_ref": c.external_ref, "created_at": c.created_at.isoformat()}


def like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.post("", status_code=201)
async def create(body: CustomerIn, p: Principal = Depends(require("customers:write")), db: AsyncSession = Depends(get_db)):
    # Deliberately no merging or de-duplication: two customers may share a phone number, and an
    # unverified number alone is not proof that they are the same person.
    c = Customer(business_id=p.business_id, **body.model_dump())
    db.add(c)
    await db.commit()
    return out(c)


@router.get("")
async def list_customers(q: str | None = Query(None, max_length=100), page: int = Query(1, ge=1),
                         page_size: int = Query(20, ge=1, le=100),
                         p: Principal = Depends(require("customers:read")), db: AsyncSession = Depends(get_db)):
    where = [Customer.business_id == p.business_id]
    if q and q.strip():
        pat = f"%{like_escape(q.strip().lower())}%"
        where.append(or_(*[func.lower(col).like(pat, escape="\\") for col in
                           (Customer.full_name, Customer.email, Customer.phone, Customer.external_ref)]))
    total = (await db.execute(select(func.count()).select_from(Customer).where(*where))).scalar_one()
    rows = (await db.execute(select(Customer).where(*where).order_by(Customer.full_name, Customer.id)
                             .limit(page_size).offset((page - 1) * page_size))).scalars().all()
    return {"items": [out(c) for c in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/{customer_id}")
async def read(customer_id: UUID, p: Principal = Depends(require("customers:read")), db: AsyncSession = Depends(get_db)):
    c = await get_customer(db, p.business_id, customer_id)
    if c is None:
        raise HTTPException(404, "Customer not found")
    return out(c)


@router.patch("/{customer_id}")
async def update(customer_id: UUID, body: CustomerPatch, p: Principal = Depends(require("customers:write")),
                 db: AsyncSession = Depends(get_db)):
    c = await get_customer(db, p.business_id, customer_id)
    if c is None:
        raise HTTPException(404, "Customer not found")
    for field in body.model_fields_set:
        value = getattr(body, field)
        if field == "full_name" and value is None:
            raise HTTPException(422, "full_name cannot be empty")
        setattr(c, field, value)
    await db.commit()
    return out(c)
