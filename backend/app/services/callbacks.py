"""Callback requests: the honest fallback when nobody can take a call. Every query is scoped to one business.

A callback is a request that a person phones the caller back. It is NOT a scheduled call: nothing dials anyone, and the
assistant must never promise a time unless a person later records one.
"""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import CallbackRequest, Customer, Department
from app.services import audit
from app.services.cases import RuleError
from app.services.telephony.context import HandoverContext

STATUSES = ("pending", "contacted", "done", "cancelled")
NEXT: dict[str, tuple[str, ...]] = {"pending": ("contacted", "done", "cancelled"), "contacted": ("pending", "done", "cancelled"), "done": (), "cancelled": ()}
_PHONE = re.compile(r"^\+?[0-9][0-9 ()\-]{5,19}$")


def clean_phone(text: str) -> str:
    phone = (text or "").strip()
    if not _PHONE.match(phone):
        raise RuleError("Give a phone number with digits only, such as +233 20 000 0000.")
    return phone


async def create_callback(db: AsyncSession, business_id: UUID, *, phone: str, reason: str, source: str, actor_user_id: UUID | None = None,
                          department_id: UUID | None = None, customer_id: UUID | None = None, caller_name: str | None = None,
                          preferred_time: str | None = None, context: HandoverContext | None = None) -> CallbackRequest:
    phone = clean_phone(phone)
    if not reason.strip():
        raise RuleError("Say what the callback is about.")
    if department_id is not None and (await db.execute(select(Department.id).where(Department.id == department_id, Department.business_id == business_id))).first() is None:
        raise RuleError("That department does not exist.")
    if customer_id is not None and (await db.execute(select(Customer.id).where(Customer.id == customer_id, Customer.business_id == business_id))).first() is None:
        raise RuleError("That customer does not exist.")
    row = CallbackRequest(business_id=business_id, department_id=department_id, customer_id=customer_id, caller_name=(caller_name or "").strip() or None,
                          phone=phone, reason=reason.strip(), preferred_time=(preferred_time or "").strip() or None,
                          context=context.model_dump() if context else {}, source=source)
    db.add(row)
    await db.flush()
    audit.record(db, business_id, actor_user_id, "callback.created", callback_id=row.id, department_id=department_id, source=source)
    return row


async def get_callback(db: AsyncSession, business_id: UUID, callback_id: UUID) -> CallbackRequest | None:
    return (await db.execute(select(CallbackRequest).where(CallbackRequest.id == callback_id, CallbackRequest.business_id == business_id))).scalar_one_or_none()


async def set_status(db: AsyncSession, business_id: UUID, row: CallbackRequest, status: str, note: str | None, actor_user_id: UUID | None) -> None:
    if status != row.status and status not in NEXT[row.status]:
        raise RuleError(f"A {row.status} callback cannot become {status}.")
    before = row.status
    row.status = status
    if note is not None:
        row.note = note.strip() or None
    audit.record(db, business_id, actor_user_id, "callback.updated", callback_id=row.id, status_from=before, status_to=status)


async def count_open(db: AsyncSession, business_id: UUID) -> int:
    return (await db.execute(select(func.count()).select_from(CallbackRequest).where(
        CallbackRequest.business_id == business_id, CallbackRequest.status.in_(("pending", "contacted"))))).scalar_one()
