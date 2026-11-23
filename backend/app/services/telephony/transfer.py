"""Route a live call to a department's people, honestly.

Rules (from the product brief): the department is looked up inside the caller's business only; success is reported
only when the provider confirms it; when a department is closed, not taking transfers, has nobody reachable or every
attempt fails, the next configured fallback department is tried (inside the same business, never looping, within one
shared budget of attempts) and, if that also fails, the caller gets an honest next step (take a callback request).
Every routing decision is written to the audit log WITHOUT phone numbers, names or what the caller said.
Still simulated: no real provider adapter exists, so nothing here places a real call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Business, Department, Employee
from app.services import audit
from app.services.telephony.context import HandoverContext
from app.services.telephony.interfaces import TelephonyProvider, TransferOutcome, TransferTarget
from app.services.telephony.schedule import is_open

MAX_ATTEMPTS = 3   # total calls placed per routing request, across every department tried
MAX_HOPS = 3       # departments considered: the one asked for plus at most two fallbacks


class Decision(str, Enum):
    TRANSFERRED = "transferred"
    NOBODY_AVAILABLE = "nobody_available"
    ALL_ATTEMPTS_FAILED = "all_attempts_failed"
    DEPARTMENT_CLOSED = "department_closed"
    UNKNOWN_DEPARTMENT = "unknown_department"


@dataclass(frozen=True)
class TransferDecision:
    decision: Decision
    attempts: int
    simulated: bool
    # What the assistant may truthfully say next.
    next_step: str  # "connected" | "offer_callback" | "ask_which_department"
    department_id: UUID | None = None      # the department that answered, or the one asked for
    tried: tuple[UUID, ...] = ()
    fallback_used: bool = False
    briefing: str = ""                      # for the receiving party; empty when no context was given
    reasons: tuple[str, ...] = field(default=())  # per department tried: closed / not_accepting / nobody_available / no_answer

    @property
    def connected(self) -> bool:
        return self.decision is Decision.TRANSFERRED


class TransferService:
    def __init__(self, provider: TelephonyProvider, max_attempts: int = MAX_ATTEMPTS):
        self._provider = provider
        self._max = max_attempts

    @property
    def simulated(self) -> bool:
        return self._provider.simulated

    async def transfer_to_department(self, db: AsyncSession, business_id: UUID, department_id: UUID, call_ref: str,
                                     reason_code: str, actor_user_id: UUID | None = None, *,
                                     context: HandoverContext | None = None, now: datetime | None = None) -> TransferDecision:
        sim = self._provider.simulated
        first = await self._department(db, business_id, department_id)
        if first is None:  # also what another business's department looks like
            return TransferDecision(Decision.UNKNOWN_DEPARTMENT, 0, sim, "ask_which_department")
        tz_default = (await db.execute(select(Business.timezone).where(Business.id == business_id))).scalar_one_or_none() or "UTC"
        briefing = context.briefing() if context else ""

        tried: list[UUID] = []
        reasons: list[str] = []
        outcomes: list[str] = []
        budget = self._max
        dept: Department | None = first
        answered: UUID | None = None
        while dept is not None and dept.id not in tried and len(tried) < MAX_HOPS:
            tried.append(dept.id)
            if not dept.accepts_transfers:
                reasons.append("not_accepting")
            elif not is_open(dept.hours, dept.timezone or tz_default, now):
                reasons.append("closed")
            else:
                people = (await db.execute(
                    select(Employee).where(Employee.business_id == business_id, Employee.department_id == dept.id, Employee.status == "active",
                                           Employee.available.is_(True), Employee.phone.is_not(None))
                    .order_by(Employee.routing_priority, Employee.full_name, Employee.id)
                )).scalars().all()
                reachable = [e for e in people if (e.phone or "").strip()]
                if not reachable:
                    reasons.append("nobody_available")
                else:
                    rang = 0
                    for emp in reachable:
                        if budget <= 0:
                            break
                        budget -= 1
                        rang += 1
                        result = await self._provider.transfer_call(call_ref, TransferTarget(emp.phone.strip(), dept.name, (emp.extension or "").strip() or None))
                        outcomes.append(result.outcome.value)
                        if result.outcome is TransferOutcome.CONFIRMED:
                            answered = dept.id
                            break
                    if answered:
                        break
                    reasons.append("no_answer" if rang else "attempt_limit")
            if budget <= 0:
                break
            dept = await self._department(db, business_id, dept.fallback_department_id) if dept.fallback_department_id else None

        fallback_used = answered is not None and answered != first.id
        if answered:
            return await self._finish(db, business_id, actor_user_id, first.id, reason_code, Decision.TRANSFERRED, outcomes, sim, "connected",
                                      tried, reasons, fallback_used, bool(context), briefing, answered)
        if reasons and all(r in ("closed", "not_accepting") for r in reasons):
            decision = Decision.DEPARTMENT_CLOSED
        elif outcomes:
            decision = Decision.ALL_ATTEMPTS_FAILED
        else:
            decision = Decision.NOBODY_AVAILABLE
        return await self._finish(db, business_id, actor_user_id, first.id, reason_code, decision, outcomes, sim, "offer_callback",
                                  tried, reasons, False, bool(context), briefing, first.id)

    @staticmethod
    async def _department(db: AsyncSession, business_id: UUID, department_id: UUID) -> Department | None:
        return (await db.execute(select(Department).where(Department.id == department_id, Department.business_id == business_id))).scalar_one_or_none()

    async def _finish(self, db, business_id, actor, asked_id, reason, decision, outcomes, sim, next_step, tried, reasons, fallback_used,
                      had_context, briefing, department_id) -> TransferDecision:
        audit.record(db, business_id, actor, "call.transfer", department_id=asked_id, answered_department_id=department_id if decision is Decision.TRANSFERRED else None,
                     decision=decision.value, attempts=len(outcomes), outcomes=outcomes, reason=reason, provider=self._provider.name,
                     simulated=sim, tried=[str(t) for t in tried], reasons=reasons, fallback_used=fallback_used, had_context=had_context)
        await db.commit()
        return TransferDecision(decision, len(outcomes), sim, next_step, department_id, tuple(tried), fallback_used, briefing, tuple(reasons))
