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

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import Department
from app.services import knowledge
from app.services.cases import Actor, RuleError, create_case
from app.services.callbacks import create_callback
from app.services.telephony.context import HandoverContext
from app.services.telephony.transfer import Decision, TransferService
from app.services.voice.business_gateway import CreateCaseArgs, EscalateArgs, SearchArgs
from app.services.voice.interfaces.business_tools import BusinessToolGateway, ToolDefinition, ToolResult

class TransferArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    department: str = Field(min_length=2, max_length=100)
    reason: str = Field(default="", max_length=300)
    context: HandoverContext | None = None  # what the caller already told you, so the next person does not ask again


class HandoverArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    department: str = Field(min_length=2, max_length=100)
    reason: str = Field(default="", max_length=300)
    context: HandoverContext | None = None


class CallbackArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: str = Field(max_length=30)
    reason: str = Field(min_length=2, max_length=500)
    department: str | None = Field(default=None, max_length=100)
    caller_name: str | None = Field(default=None, max_length=200)
    preferred_time: str | None = Field(default=None, max_length=100)
    context: HandoverContext | None = None


CustomerResolver = Callable[[UUID, UUID], Awaitable[UUID | None]]  # (business_id, session_id) -> customer_id

_TOOLS = {
    "search_knowledge": (SearchArgs, "Look up approved business information (hours, policies, procedures). Answer only from what it returns."),
    "create_case": (CreateCaseArgs, "Log the caller's problem as a case for the team. Only works once the caller is identified."),
    "escalate_to_human": (EscalateArgs, "Hand the call over to a person."),
}
_ROUTING_TOOLS = {
    "transfer_to_department": (TransferArgs, "Connect the caller to a department's people. Only say they are connected if the result says the provider confirmed it. Pass what the caller already told you in context."),
    "hand_over_to_department_assistant": (HandoverArgs, "Pass this same call to a department's assistant (no telephone, no person). Pass everything the caller already told you in context so they are not asked again."),
    "request_callback": (CallbackArgs, "Record a request for a person to phone the caller back, when nobody can take the call now. Needs the caller's phone number. It is a request, not a booked time."),
}
_REFUSED = ToolResult(ok=False, summary="That action is not available.")


class DatabaseBusinessGateway(BusinessToolGateway):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], customer_resolver: CustomerResolver,
                 transfer: TransferService | None = None) -> None:
        self._factory = session_factory
        self._resolve_customer = customer_resolver
        self._transfer = transfer

    def _tools(self) -> dict:
        tools = dict(_TOOLS)
        tools["request_callback"] = _ROUTING_TOOLS["request_callback"]
        tools["hand_over_to_department_assistant"] = _ROUTING_TOOLS["hand_over_to_department_assistant"]
        if self._transfer is not None:
            tools["transfer_to_department"] = _ROUTING_TOOLS["transfer_to_department"]
        return tools

    async def list_tools(self, business_id: UUID, agent_id: UUID | None) -> list[ToolDefinition]:
        return [ToolDefinition(name=n, description=d, parameters=m.model_json_schema()) for n, (m, d) in self._tools().items()]

    async def execute(self, *, business_id: UUID, session_id: UUID, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        tools = self._tools()
        if tool_name not in tools:
            return _REFUSED
        try:
            args = tools[tool_name][0].model_validate(arguments)
        except ValidationError:
            return ToolResult(ok=False, summary="The request details were incomplete or invalid. Nothing was done.")
        if isinstance(args, HandoverArgs):
            return await self._do_handover(business_id, args)
        if isinstance(args, TransferArgs):
            return await self._do_transfer(business_id, session_id, args)
        if isinstance(args, CallbackArgs):
            return await self._do_callback(business_id, session_id, args)
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

    async def _do_transfer(self, business_id: UUID, session_id: UUID, args: TransferArgs) -> ToolResult:
        assert self._transfer is not None
        async with self._factory() as db:
            dept_id = (await db.execute(select(Department.id).where(
                Department.business_id == business_id, func.lower(Department.name) == args.department.strip().lower()))).scalar_one_or_none()
            if dept_id is None:
                names = (await db.execute(select(Department.name).where(Department.business_id == business_id).order_by(Department.name))).scalars().all()
                return ToolResult(ok=False, summary="That department does not exist. Nothing was transferred. Available: " + (", ".join(names) or "none"))
            decision = await self._transfer.transfer_to_department(db, business_id, dept_id, str(session_id), "assistant_request", context=args.context)
            answered = (await db.execute(select(Department.name).where(Department.id == decision.department_id, Department.business_id == business_id))).scalar_one_or_none()
        data = {"decision": decision.decision.value, "simulated": decision.simulated, "fallback_used": decision.fallback_used}
        if decision.connected:
            who = answered or args.department
            if decision.simulated:
                return ToolResult(ok=True, data=data, summary=f"SIMULATED transfer to {who}: this is a test environment and no real call was moved. Do not tell the caller they are now connected; "
                                  "say that on a live call they would be connected to that team.")
            return ToolResult(ok=True, data=data, summary=f"The telephone provider confirmed the transfer to {who}. Tell the caller they are being connected.")
        if decision.decision is Decision.UNKNOWN_DEPARTMENT:
            return ToolResult(ok=False, data=data, summary="That department does not exist. Nothing was transferred. Ask which team the caller needs.")
        why = {Decision.DEPARTMENT_CLOSED: "The team is closed or not taking transfers right now.",
               Decision.NOBODY_AVAILABLE: "Nobody in the team is available to take the call.",
               Decision.ALL_ATTEMPTS_FAILED: "Nobody answered."}[decision.decision]
        return ToolResult(ok=False, data=data, summary=f"{why} Nothing was transferred. Offer to record a callback request with request_callback, "
                          "use what the caller already told you, and do not ask for it again.")

    async def _do_handover(self, business_id: UUID, args: HandoverArgs) -> ToolResult:
        async with self._factory() as db:
            dept = (await db.execute(select(Department).where(
                Department.business_id == business_id, func.lower(Department.name) == args.department.strip().lower()))).scalar_one_or_none()
            if dept is None:
                names = (await db.execute(select(Department.name).where(Department.business_id == business_id).order_by(Department.name))).scalars().all()
                return ToolResult(ok=False, summary="That department does not exist. Nothing was changed. Available: " + (", ".join(names) or "none"))
            name, description = dept.name, dept.description
        lines = [f"You are now the {name} assistant for this business, taking over the same call from the general assistant."]
        if description:
            lines.append(f"About the {name} team: {description}")
        if args.reason:
            lines.append(f"Why the call was passed to you: {args.reason}")
        if args.context is not None and args.context.briefing():
            lines.append("Briefing (the caller must not be asked for this again):\n" + args.context.briefing())
        return ToolResult(
            ok=True, data={"department": name, "focus": "\n".join(lines)},
            summary=f"The call is now with the {name} assistant. This is an assistant, not a person, so do not say a person was connected. "
                    "Say in one short sentence who you are now, and carry on without repeating questions already answered.")

    async def _do_callback(self, business_id: UUID, session_id: UUID, args: CallbackArgs) -> ToolResult:
        customer_id = await self._resolve_customer(business_id, session_id)
        async with self._factory() as db:
            try:
                department_id = await self._department_id(db, business_id, args.department)
                row = await create_callback(db, business_id, phone=args.phone, reason=args.reason, source="ai", department_id=department_id, customer_id=customer_id,
                                            caller_name=args.caller_name, preferred_time=args.preferred_time, context=args.context)
            except RuleError as err:
                await db.rollback()
                return ToolResult(ok=False, summary=err.message + " Nothing was recorded.")
            await db.commit()
        return ToolResult(ok=True, data={"callback_id": str(row.id)},
                          summary="Callback request recorded for the team. It is a request, not a booked time: do not promise when someone will call.")

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
