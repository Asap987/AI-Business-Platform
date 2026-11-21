from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SessionState(str, Enum):
    CONNECTING = "connecting"
    LISTENING = "listening"  # waiting for / receiving customer speech
    THINKING = "thinking"  # reasoning and tools running
    SPEAKING = "speaking"  # AI audio is playing; customer may interrupt
    ESCALATING = "escalating"  # handing over to a human
    ENDED = "ended"


class Speaker(str, Enum):
    CUSTOMER = "customer"
    AI = "ai"
    SYSTEM = "system"


class TranscriptTurn(BaseModel):
    speaker: Speaker
    text: str
    language_code: str | None = None
    at: datetime = Field(default_factory=_now)
    # True when the customer cut the AI off before it finished this turn.
    interrupted: bool = False


class ToolCallRecord(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    ok: bool
    # Result summary as confirmed by the backend, never as claimed by the model.
    result_summary: str | None = None
    at: datetime = Field(default_factory=_now)


class EscalationStatus(BaseModel):
    requested: bool = False
    reason: str | None = None
    case_id: UUID | None = None
    at: datetime | None = None


class VoiceSession(BaseModel):
    """
    Live state for one call. Held in the session store only while the call is
    active; what must outlive the call is written to the permanent
    conversations/cases tables at the end (or at checkpoints).
    """

    session_id: UUID = Field(default_factory=uuid4)
    # Every access to this session must be checked against this business.
    business_id: UUID
    customer_id: UUID | None = None  # only when reliably identified
    call_id: str | None = None  # telephony provider's call identifier
    agent_id: UUID | None = None
    state: SessionState = SessionState.CONNECTING
    language_code: str = "en"
    unsupported_language_attempts: int = 0
    voice_id: str | None = None
    recording_consent: bool = False
    redact_contact_details: bool | None = None  # business privacy setting; None = platform default
    transcript: list[TranscriptTurn] = Field(default_factory=list)
    tool_history: list[ToolCallRecord] = Field(default_factory=list)
    escalation: EscalationStatus = Field(default_factory=EscalationStatus)
    started_at: datetime = Field(default_factory=_now)
    last_activity_at: datetime = Field(default_factory=_now)
    ended_at: datetime | None = None
