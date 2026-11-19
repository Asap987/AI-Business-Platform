from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    """A business action the AI is allowed to request."""

    name: str
    description: str
    # JSON Schema for the arguments, passed to the model as the tool schema.
    parameters: dict[str, Any]


class ToolResult(BaseModel):
    """Outcome as confirmed by the backend. The AI may only report what is here."""

    ok: bool
    # Plain-language facts the AI may relay (e.g. "Case 4821 created for Technical").
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    # Set when the action needs a human to approve it (refunds, adjustments, ...).
    requires_human_approval: bool = False


class BusinessToolGateway(ABC):
    """
    The only way the voice engine touches business data or operations.
    Knowledge lookup, case creation and department requests live behind this
    interface in the existing application services; speech and model adapters
    contain no business rules.

    Implementations MUST scope every call to business_id and enforce that
    business's permissions, regardless of what the model asked for.
    """

    @abstractmethod
    async def list_tools(self, business_id: UUID, agent_id: UUID | None) -> list[ToolDefinition]:
        """Only the tools this business has enabled for this agent."""

    @abstractmethod
    async def execute(
        self,
        *,
        business_id: UUID,
        session_id: UUID,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult: ...
