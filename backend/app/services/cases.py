"""
Case and customer rules, shared by the HTTP API and the voice tools so both
follow the same validation, tenant scoping and history recording.
Every function takes business_id and only ever touches that business's rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Case, CaseEvent, Conversation, Customer, Department, Employee

STATUSES = ("open", "in_progress", "waiting_customer", "waiting_department", "resolved", "closed")
PRIORITIES = ("low", "medium", "high", "urgent")

_WAITING = {"waiting_customer", "waiting_department"}
TRANSITIONS: dict[str, set[str]] = {
    "open": {"in_progress", "resolved"} | _WAITING,
    "in_progress": {"open", "resolved"} | _WAITING,
    "waiting_customer": {"open", "in_progress", "resolved", "waiting_department"},
    "waiting_department": {"open", "in_progress", "resolved", "waiting_customer"},
    "resolved": {"closed", "in_progress"},  # reopening is allowed, closing is final
    "closed": set(),
}


class RuleError(Exception):
    """A request that breaks a business rule. `status` is the HTTP code the API should use."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.message, self.status = message, status


@dataclass(frozen=True)
class Actor:
    kind: str  # "user" | "ai" | "system"
    user_id: UUID | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get_customer(db: AsyncSession, business_id: UUID, customer_id: UUID) -> Customer | None:
    return (await db.execute(select(Customer).where(Customer.id == customer_id, Customer.business_id == business_id))).scalar_one_or_none()


async def get_case(db: AsyncSession, business_id: UUID, case_id: UUID) -> Case | None:
    return (await db.execute(select(Case).where(Case.id == case_id, Case.business_id == business_id))).scalar_one_or_none()


async def _check_department(db, business_id, department_id) -> None:
    if department_id is not None and (await db.execute(
        select(Department.id).where(Department.id == department_id, Department.business_id == business_id)
    )).scalar_one_or_none() is None:
        raise RuleError("That department does not exist.")


async def _check_employee(db, business_id, employee_id) -> None:
    if employee_id is None:
        return
    emp = (await db.execute(select(Employee).where(Employee.id == employee_id, Employee.business_id == business_id))).scalar_one_or_none()
    if emp is None:
        raise RuleError("That employee does not exist.")
    if emp.status != "active":
        raise RuleError("That employee is not active, so cases cannot be assigned to them.")


async def _check_conversation(db, business_id, customer_id, conversation_id) -> None:
    if conversation_id is None:
        return
    conv = (await db.execute(select(Conversation).where(Conversation.id == conversation_id, Conversation.business_id == business_id))).scalar_one_or_none()
    if conv is None:
        raise RuleError("That conversation does not exist.")
    if conv.customer_id != customer_id:
        raise RuleError("That conversation belongs to a different customer.")


def record(db: AsyncSession, case: Case, actor: Actor, kind: str, detail: dict[str, Any] | None = None) -> None:
    db.add(CaseEvent(business_id=case.business_id, case_id=case.id, actor_user_id=actor.user_id,
                     actor_kind=actor.kind, kind=kind, detail=detail or {}))


async def create_case(
    db: AsyncSession, business_id: UUID, actor: Actor, *, customer_id: UUID, title: str,
    description: str | None = None, priority: str = "medium", department_id: UUID | None = None,
    conversation_id: UUID | None = None,
) -> Case:
    if priority not in PRIORITIES:
        raise RuleError("Unknown priority.")
    if await get_customer(db, business_id, customer_id) is None:
        raise RuleError("That customer does not exist.", 404)
    await _check_department(db, business_id, department_id)
    await _check_conversation(db, business_id, customer_id, conversation_id)
    case = Case(business_id=business_id, customer_id=customer_id, title=title.strip(), description=description,
                priority=priority, department_id=department_id, conversation_id=conversation_id, status="open")
    db.add(case)
    await db.flush()
    record(db, case, actor, "created", {"priority": priority, "department_id": str(department_id) if department_id else None})
    return case


async def update_case(db: AsyncSession, business_id: UUID, actor: Actor, case: Case, changes: dict[str, Any]) -> Case:
    """`changes` holds only the fields the caller sent (None means 'clear' for the nullable ones)."""
    assert case.business_id == business_id
    if case.status == "closed":
        raise RuleError("A closed case cannot be changed.", 409)
    detail: dict[str, Any] = {}

    if "priority" in changes:
        if changes["priority"] not in PRIORITIES:
            raise RuleError("Unknown priority.")
        if changes["priority"] != case.priority:
            detail["priority"] = [case.priority, changes["priority"]]
            case.priority = changes["priority"]
    if "department_id" in changes:
        await _check_department(db, business_id, changes["department_id"])
        if changes["department_id"] != case.department_id:
            detail["department_id"] = [str(case.department_id) if case.department_id else None,
                                       str(changes["department_id"]) if changes["department_id"] else None]
            case.department_id = changes["department_id"]
    if "assigned_employee_id" in changes:
        await _check_employee(db, business_id, changes["assigned_employee_id"])
        if changes["assigned_employee_id"] != case.assigned_employee_id:
            detail["assigned_employee_id"] = [str(case.assigned_employee_id) if case.assigned_employee_id else None,
                                              str(changes["assigned_employee_id"]) if changes["assigned_employee_id"] else None]
            case.assigned_employee_id = changes["assigned_employee_id"]
    for text_field in ("title", "description", "resolution_notes"):
        if text_field in changes and changes[text_field] != getattr(case, text_field):
            setattr(case, text_field, changes[text_field])
            detail.setdefault("fields_changed", []).append(text_field)  # content is not copied into the history

    if "status" in changes and changes["status"] != case.status:
        new = changes["status"]
        if new not in STATUSES:
            raise RuleError("Unknown status.")
        if new not in TRANSITIONS[case.status]:
            raise RuleError(f"A case cannot go from {case.status} to {new}.", 409)
        if new == "resolved" and not (case.resolution_notes or "").strip():
            raise RuleError("Add resolution notes before resolving a case.")
        detail["status"] = [case.status, new]
        case.status = new
        case.resolved_at = _now() if new in ("resolved", "closed") and case.resolved_at is None else (
            None if new not in ("resolved", "closed") else case.resolved_at
        )

    if detail:
        kind = "status_changed" if "status" in detail else "assigned" if "assigned_employee_id" in detail else "updated"
        record(db, case, actor, kind, detail)
    return case
