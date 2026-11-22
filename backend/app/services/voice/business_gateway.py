"""
Prototype business gateway backed by in-memory data. It shows how every
tool call is scoped to one business, validated, permission-checked and
reported truthfully. A production gateway would call the real application
services and database behind the same ``BusinessToolGateway`` interface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, ValidationError

from app.services.voice.interfaces.business_tools import BusinessToolGateway, ToolDefinition, ToolResult


class SearchArgs(BaseModel):
    query: str = Field(min_length=2, max_length=300)


class CreateCaseArgs(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=2000)
    department: str | None = Field(default=None, max_length=100)


class EscalateArgs(BaseModel):
    reason: str = Field(min_length=2, max_length=500)


TOOLS: dict[str, tuple[type[BaseModel], str]] = {
    "search_knowledge": (SearchArgs, "Look up approved business information (hours, policies, procedures)."),
    "create_case": (CreateCaseArgs, "Log the customer's problem as a case for the right department."),
    "escalate_to_human": (EscalateArgs, "Hand the call over to a person."),
}


@dataclass
class CaseRecord:
    case_id: UUID
    session_id: UUID
    title: str
    description: str
    department: str | None


@dataclass
class BusinessData:
    """Everything the gateway may use for ONE business."""

    knowledge: list[str] = field(default_factory=list)
    departments: list[str] = field(default_factory=list)
    enabled_tools: set[str] = field(default_factory=lambda: set(TOOLS))
    cases: list[CaseRecord] = field(default_factory=list)
    escalations: list[tuple[UUID, str]] = field(default_factory=list)  # (session_id, reason)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


class InMemoryBusinessGateway(BusinessToolGateway):
    def __init__(self) -> None:
        self._data: dict[UUID, BusinessData] = {}

    def register_business(self, business_id: UUID, data: BusinessData | None = None) -> BusinessData:
        self._data[business_id] = data or BusinessData()
        return self._data[business_id]

    def data_for(self, business_id: UUID) -> BusinessData | None:
        return self._data.get(business_id)

    async def list_tools(self, business_id: UUID, agent_id: UUID | None) -> list[ToolDefinition]:
        data = self._data.get(business_id)
        if data is None:
            return []
        return [
            ToolDefinition(name=name, description=desc, parameters=model.model_json_schema())
            for name, (model, desc) in TOOLS.items()
            if name in data.enabled_tools
        ]

    async def execute(
        self, *, business_id: UUID, session_id: UUID, tool_name: str, arguments: dict[str, Any]
    ) -> ToolResult:
        data = self._data.get(business_id)
        # Same answer for "unknown business" and "tool disabled": nothing leaks about other tenants.
        if data is None or tool_name not in TOOLS or tool_name not in data.enabled_tools:
            return ToolResult(ok=False, summary="That action is not available.")
        model = TOOLS[tool_name][0]
        try:
            args = model.model_validate(arguments)
        except ValidationError:
            return ToolResult(ok=False, summary="The request details were incomplete or invalid. Nothing was done.")

        if isinstance(args, SearchArgs):
            wanted = _words(args.query)
            scored = sorted(((len(wanted & _words(doc)), doc) for doc in data.knowledge), reverse=True)
            hits = [doc for score, doc in scored if score > 0][:3]
            if not hits:
                return ToolResult(ok=True, summary="No matching information was found.", data={"results": []})
            return ToolResult(ok=True, summary=" ".join(hits), data={"results": hits})

        if isinstance(args, CreateCaseArgs):
            if args.department is not None and args.department not in data.departments:
                return ToolResult(
                    ok=False,
                    summary="That department does not exist. Available: " + ", ".join(data.departments),
                )
            record = CaseRecord(uuid4(), session_id, args.title, args.description, args.department)
            data.cases.append(record)
            where = f" for {args.department}" if args.department else ""
            return ToolResult(
                ok=True, summary=f"Case created{where}. A team member will follow up.",
                data={"case_id": str(record.case_id)},
            )

        assert isinstance(args, EscalateArgs)
        data.escalations.append((session_id, args.reason))
        return ToolResult(
            ok=True, summary="The call has been marked for a team member to take over.",
            data={"escalated": True},
        )
