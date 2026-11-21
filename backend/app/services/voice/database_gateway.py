"""
Database-backed business gateway for the voice assistant.

Offers what the real backend can do: look up the business's published knowledge-base
documents, log a case and flag a hand-over. Knowledge search is read-only, scoped to the
business, and returns at most three short passages, so only what is relevant to the question
reaches the AI provider. All writes go through
app.services.cases, the same rules the HTTP API uses, scoped to the business,
and are recorded in the case history as made by the AI.

A case needs a customer. The voice layer must supply a resolver that returns a
customer id only when the caller has been reliably identified; otherwise the
case is refused and the assistant is told to offer a person instead.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import Department
from app.services import knowledge
from app.services.cases import Actor, RuleError, create_case
from app.services.voice.business_gateway import CreateCaseArgs, EscalateArgs, SearchArgs
from app.services.voice.interfaces.business_tools import BusinessToolGateway, ToolDefinition, ToolResult

CustomerResolver = Callable[[UUID, UUID], Awaitable[UUID | None]]  # (business_id, session_id) -> customer_id

_TOOLS = {
    "search_knowledge": (SearchArgs, "Look up approved business information (hours, policies, procedures). Answer only from what it returns."),
    "create_case": (CreateCaseArgs, "Log the caller's problem as a case for the team. Only works once the caller is identified."),
    "escalate_to_human": (EscalateArgs, "Hand the call over to a person."),
}
_REFUSED = ToolResult(ok=False, summary="That action is not available.")


class DatabaseBusinessGateway(BusinessToolGateway):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], customer_resolver: CustomerResolver) -> None:
        self._factory = session_factory
        self._resolve_customer = customer_resolver

    async def list_tools(self, business_id: UUID, agent_id: UUID | None) -> list[ToolDefinition]:
        return [ToolDefinition(name=n, description=d, parameters=m.model_json_schema()) for n, (m, d) in _TOOLS.items()]

    async def execute(self, *, business_id: UUID, session_id: UUID, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        if tool_name not in _TOOLS:
            return _REFUSED
        try:
            args = _TOOLS[tool_name][0].model_validate(arguments)
        except ValidationError:
            return ToolResult(ok=False, summary="The request details were incomplete or invalid. Nothing was done.")
        if isinstance(args, SearchArgs):
            async with self._factory() as db:
                hits = await knowledge.search(db, business_id, args.query)
            if not hits:
                return ToolResult(ok=True, summary="No matching information was found. Do not guess; offer to connect a team member.",
                                  data={"results": []})
            passages = [f"[{h.title}] {h.text}"[:900] for h in hits]
            return ToolResult(ok=True, summary="\n\n".join(passages), data={"results": [h.title for h in hits]})

        customer_id = await self._resolve_customer(business_id, session_id)
        actor = Actor("ai")

        if isinstance(args, CreateCaseArgs):
            if customer_id is None:
                return ToolResult(ok=False, summary="The caller has not been identified, so no case was logged. Offer to connect them to a team member.")
            async with self._factory() as db:
                try:
                    department_id = await self._department_id(db, business_id, args.department)
                    case = await create_case(db, business_id, actor, customer_id=customer_id, title=args.title,
                                             description=args.description or None, department_id=department_id)
                except RuleError as err:
                    await db.rollback()
                    return ToolResult(ok=False, summary=err.message)
                await db.commit()
            where = f" for {args.department}" if args.department else ""
            return ToolResult(ok=True, summary=f"Case created{where}. A team member will follow up.", data={"case_id": str(case.id)})

        assert isinstance(args, EscalateArgs)
        if customer_id is None:
            # Nothing can be stored without a customer; the live session is still flagged for hand-over by the caller.
            return ToolResult(ok=True, summary="The call has been marked for a team member to take over.", data={"escalated": True})
        async with self._factory() as db:
            try:
                case = await create_case(db, business_id, actor, customer_id=customer_id, title="Call handed to a person",
                                         description=args.reason, priority="urgent")
            except RuleError as err:
                await db.rollback()
                return ToolResult(ok=False, summary=err.message)
            await db.commit()
        return ToolResult(ok=True, summary="The call has been marked for a team member to take over.",
                          data={"escalated": True, "case_id": str(case.id)})

    @staticmethod
    async def _department_id(db: AsyncSession, business_id: UUID, name: str | None) -> UUID | None:
        if not name:
            return None
        found = (await db.execute(select(Department.id).where(
            Department.business_id == business_id, func.lower(Department.name) == name.strip().lower()))).scalar_one_or_none()
        if found is None:
            names = (await db.execute(select(Department.name).where(Department.business_id == business_id).order_by(Department.name))).scalars().all()
            raise RuleError("That department does not exist. Available: " + (", ".join(names) or "none"))
        return found
