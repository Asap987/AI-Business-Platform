from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, Union
from uuid import UUID

from pydantic import BaseModel, Field

from app.services.voice.interfaces.business_tools import ToolDefinition, ToolResult
from app.services.voice.schemas.voice_session import TranscriptTurn


class ReasoningRequest(BaseModel):
    business_id: UUID
    session_id: UUID
    language_code: str
    # Business name, approved procedures, relevant knowledge excerpts. Built per
    # business by the conversation manager; never shared across businesses.
    business_context: str
    history: list[TranscriptTurn]
    user_text: str
    tools: list[ToolDefinition] = Field(default_factory=list)
    # Results of tools run earlier in this turn, fed back to the model.
    tool_results: list[tuple[str, ToolResult]] = Field(default_factory=list)


class ReasoningUsage(BaseModel):
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class TextDelta(BaseModel):
    """A fragment of the reply, forwarded to speech generation immediately."""

    text: str


class ToolCallRequested(BaseModel):
    call_id: str
    tool_name: str
    arguments: dict[str, Any]


class TurnCompleted(BaseModel):
    usage: ReasoningUsage
    # Structured signals for the application, produced alongside the spoken reply.
    intent: str | None = None
    sentiment: str | None = None
    urgency: str | None = None
    needs_human: bool = False


ReasoningEvent = Union[TextDelta, ToolCallRequested, TurnCompleted]


class ReasoningEngine(ABC):
    """Provider-independent reasoning. OpenAI is the first adapter."""

    @abstractmethod
    def respond_stream(self, request: ReasoningRequest) -> AsyncIterator[ReasoningEvent]:
        """Stream the reply; may emit ToolCallRequested before more text."""

    @abstractmethod
    async def health_check(self) -> bool: ...
