"""Transfer a live call to a department's people, honestly.

Rules (from the product brief): the department is looked up inside the caller's business only; success is reported
only when the provider confirms it; if nobody is available or every attempt fails, the caller gets an honest
fallback (take a message / callback) and the attempt is written to the audit log WITHOUT phone numbers or names.
Not modelled yet (no data for it): department opening hours, extensions, a separate department switchboard number.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Department, Employee
from app.services import audit
from app.services.telephony.interfaces import TelephonyProvider, TransferOutcome, TransferTarget

MAX_ATTEMPTS = 3


class Decision(str, Enum):
    TRANSFERRED = "transferred"
    NOBODY_AVAILABLE = "nobody_available"
    ALL_ATTEMPTS_FAILED = "all_attempts_failed"
    UNKNOWN_DEPARTMENT = "unknown_department"


@dataclass(frozen=True)
class TransferDecision:
    decision: Decision
    attempts: int
    simulated: bool
    # What the assistant may truthfully say next.
    next_step: str  # "connected" | "offer_callback" | "ask_which_department"

    @property
    def connected(self) -> bool:
        return self.decision is Decision.TRANSFERRED


class TransferService:
    def __init__(self, provider: TelephonyProvider, max_attempts: int = MAX_ATTEMPTS):
        self._provider = provider
        self._max = max_attempts

    async def transfer_to_department(self, db: AsyncSession, business_id: UUID, department_id: UUID, call_ref: str,
                                     reason_code: str, actor_user_id: UUID | None = None) -> TransferDecision:
        sim = self._provider.simulated
        dept = (await db.execute(select(Department).where(Department.id == department_id, Department.business_id == business_id))).scalar_one_or_none()
        if dept is None:  # also what another business's department looks like
            return TransferDecision(Decision.UNKNOWN_DEPARTMENT, 0, sim, "ask_which_department")
        people = (await db.execute(
            select(Employee).where(Employee.business_id == business_id, Employee.department_id == dept.id,
                                   Employee.status == "active", Employee.phone.is_not(None)).order_by(Employee.full_name, Employee.id)
        )).scalars().all()
        reachable = [e for e in people if (e.phone or "").strip()]
        if not reachable:
            return await self._finish(db, business_id, actor_user_id, dept.id, reason_code, Decision.NOBODY_AVAILABLE, 0, [], sim, "offer_callback")
        outcomes: list[str] = []
        for emp in reachable[: self._max]:
            result = await self._provider.transfer_call(call_ref, TransferTarget(emp.phone.strip(), dept.name))
            outcomes.append(result.outcome.value)
            if result.outcome is TransferOutcome.CONFIRMED:
                return await self._finish(db, business_id, actor_user_id, dept.id, reason_code, Decision.TRANSFERRED, len(outcomes), outcomes, sim, "connected")
        return await self._finish(db, business_id, actor_user_id, dept.id, reason_code, Decision.ALL_ATTEMPTS_FAILED, len(outcomes), outcomes, sim, "offer_callback")

    async def _finish(self, db, business_id, actor, dept_id, reason, decision, attempts, outcomes, sim, next_step) -> TransferDecision:
        audit.record(db, business_id, actor, "call.transfer", department_id=dept_id, decision=decision.value, attempts=attempts,
                     outcomes=outcomes, reason=reason, provider=self._provider.name, simulated=sim)
        await db.commit()
        return TransferDecision(decision, attempts, sim, next_step)
