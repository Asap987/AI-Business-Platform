"""
ORM mapping of migrations/0001_initial.sql and 0002. The SQL files are the
source of truth for production; these models must match them. Types are
portable so the same code runs on PostgreSQL and on SQLite in quick tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

Json = JSON().with_variant(JSONB(), "postgresql")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class _Stamped:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


def _fk(table: str, nullable: bool = False):
    return mapped_column(Uuid, ForeignKey(f"{table}.id", ondelete="CASCADE" if not nullable else "SET NULL"), nullable=nullable)


class Business(_Stamped, Base):
    __tablename__ = "businesses"
    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    industry: Mapped[str | None] = mapped_column(Text, default=None)
    country: Mapped[str | None] = mapped_column(Text, default=None)
    timezone: Mapped[str] = mapped_column(Text, default="UTC")
    status: Mapped[str] = mapped_column(String, default="active")


class Role(_Stamped, Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("business_id", "name"),)
    business_id: Mapped[UUID] = _fk("businesses")
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    permissions: Mapped[Any] = mapped_column(Json, default=list)


class User(_Stamped, Base):
    __tablename__ = "users"
    business_id: Mapped[UUID] = _fk("businesses")
    role_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("roles.id", ondelete="RESTRICT"))
    email: Mapped[str] = mapped_column(Text)  # stored lower-cased
    password_hash: Mapped[str] = mapped_column(Text)
    full_name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Set when the address is proven (invitation accepted, or verification link used). NULL for older accounts.
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class Department(_Stamped, Base):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("business_id", "name"),)
    business_id: Mapped[UUID] = _fk("businesses")
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    # Routing. hours None = always open; see app.services.telephony.schedule for the format.
    hours: Mapped[Any | None] = mapped_column(Json, default=None)
    timezone: Mapped[str | None] = mapped_column(Text, default=None)
    fallback_department_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("departments.id", ondelete="SET NULL"), default=None)
    accepts_transfers: Mapped[bool] = mapped_column(Boolean, default=True)


class Employee(_Stamped, Base):
    __tablename__ = "employees"
    business_id: Mapped[UUID] = _fk("businesses")
    user_id: Mapped[UUID | None] = _fk("users", True)
    department_id: Mapped[UUID | None] = _fk("departments", True)
    full_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text, default=None)
    phone: Mapped[str | None] = mapped_column(Text, default=None)
    job_title: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String, default="active")
    extension: Mapped[str | None] = mapped_column(Text, default=None)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    routing_priority: Mapped[int] = mapped_column(Integer, default=100)


class CallbackRequest(_Stamped, Base):
    __tablename__ = "callback_requests"
    business_id: Mapped[UUID] = _fk("businesses")
    department_id: Mapped[UUID | None] = _fk("departments", True)
    customer_id: Mapped[UUID | None] = _fk("customers", True)
    caller_name: Mapped[str | None] = mapped_column(Text, default=None)
    phone: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    preferred_time: Mapped[str | None] = mapped_column(Text, default=None)
    context: Mapped[Any] = mapped_column(Json, default=dict)
    source: Mapped[str] = mapped_column(String, default="ai")
    status: Mapped[str] = mapped_column(String, default="pending")
    note: Mapped[str | None] = mapped_column(Text, default=None)


class Agent(_Stamped, Base):
    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("business_id", "name"),)
    business_id: Mapped[UUID] = _fk("businesses")
    department_id: Mapped[UUID | None] = _fk("departments", True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String, default="draft")
    config: Mapped[Any] = mapped_column(Json, default=dict)


class Customer(_Stamped, Base):
    __tablename__ = "customers"
    business_id: Mapped[UUID] = _fk("businesses")
    full_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text, default=None)
    phone: Mapped[str | None] = mapped_column(Text, default=None)
    external_ref: Mapped[str | None] = mapped_column(Text, default=None)
    metadata_: Mapped[Any] = mapped_column("metadata", Json, default=dict)


class Conversation(_Stamped, Base):
    __tablename__ = "conversations"
    business_id: Mapped[UUID] = _fk("businesses")
    customer_id: Mapped[UUID] = _fk("customers")
    agent_id: Mapped[UUID | None] = _fk("agents", True)
    employee_id: Mapped[UUID | None] = _fk("employees", True)
    channel: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="open")
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class Case(_Stamped, Base):
    __tablename__ = "cases"
    business_id: Mapped[UUID] = _fk("businesses")
    customer_id: Mapped[UUID] = _fk("customers")
    conversation_id: Mapped[UUID | None] = _fk("conversations", True)
    department_id: Mapped[UUID | None] = _fk("departments", True)
    assigned_employee_id: Mapped[UUID | None] = _fk("employees", True)
    assigned_agent_id: Mapped[UUID | None] = _fk("agents", True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    priority: Mapped[str] = mapped_column(String, default="medium")
    status: Mapped[str] = mapped_column(String, default="open")
    resolution_notes: Mapped[str | None] = mapped_column(Text, default=None)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = _fk("users")
    business_id: Mapped[UUID] = _fk("businesses")
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CaseEvent(Base):
    """Append-only case history. The SQL migration also blocks UPDATE; rows go away only with their case."""

    __tablename__ = "case_events"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = _fk("businesses")
    case_id: Mapped[UUID] = _fk("cases")
    actor_user_id: Mapped[UUID | None] = _fk("users", True)
    actor_kind: Mapped[str] = mapped_column(String, default="user")
    kind: Mapped[str] = mapped_column(String)
    detail: Mapped[Any] = mapped_column(Json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UserInvite(Base):
    __tablename__ = "user_invites"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = _fk("businesses")
    email: Mapped[str] = mapped_column(Text)  # stored lower-cased
    role_id: Mapped[UUID] = _fk("roles")
    employee_id: Mapped[UUID | None] = _fk("employees", True)
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    invited_by: Mapped[UUID | None] = _fk("users", True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class PasswordReset(Base):
    __tablename__ = "password_resets"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = _fk("users")
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class EmailVerification(Base):
    __tablename__ = "email_verifications"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = _fk("users")
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = _fk("businesses")
    title: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text, default=None)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="published")
    created_by: Mapped[UUID | None] = _fk("users", True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = _fk("businesses")
    document_id: Mapped[UUID] = _fk("knowledge_documents")
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)


class BusinessPrivacy(Base):
    __tablename__ = "business_privacy"
    business_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True)
    ai_providers_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    redact_contact_details: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by: Mapped[UUID | None] = _fk("users", True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class AuditEvent(Base):
    """Append-only (the SQL migration blocks UPDATE). Holds field names and ids, never message text or secrets."""

    __tablename__ = "audit_events"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = _fk("businesses")
    actor_user_id: Mapped[UUID | None] = _fk("users", True)
    action: Mapped[str] = mapped_column(String)
    detail: Mapped[Any] = mapped_column(Json, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UsageSession(Base):
    """One call's measured usage and its cost ESTIMATE. Counts are measured; the cost is always an estimate from the
    price records in force when the call ended (the rates used are stored so the number stays explainable).
    No transcript text, audio or customer details are stored here."""

    __tablename__ = "usage_sessions"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = _fk("businesses")
    session_id: Mapped[UUID] = mapped_column(Uuid)
    conversation_id: Mapped[UUID | None] = _fk("conversations", True)
    source: Mapped[str] = mapped_column(String, default="test_call")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    stt_seconds: Mapped[int] = mapped_column(Integer, default=0)  # whole seconds of audio sent for recognition
    tts_characters: Mapped[int] = mapped_column(Integer, default=0)
    llm_requests: Mapped[int] = mapped_column(Integer, default=0)
    llm_usage: Mapped[Any] = mapped_column(Json, default=list)  # [{"model","input_tokens","output_tokens"}] summed per model
    failed_requests: Mapped[int] = mapped_column(Integer, default=0)
    retries: Mapped[int] = mapped_column(Integer, default=0)  # speech-connection retries only; OpenAI SDK retries are not visible to us
    turns: Mapped[int] = mapped_column(Integer, default=0)
    latency_avg_ms: Mapped[int | None] = mapped_column(Integer, default=None)  # customer message to first audio, per turn
    latency_max_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    cost_micro_usd: Mapped[int] = mapped_column(BigInteger, default=0)  # priced lines only; 1 000 000 = 1 US dollar
    cost_complete: Mapped[bool] = mapped_column(Boolean, default=False)  # False when some used item had no price record
    missing_rates: Mapped[Any] = mapped_column(Json, default=list)
    pricing_snapshot: Mapped[Any] = mapped_column(Json, default=dict)


class PriceRecord(Base):
    """Platform-wide provider price (NOT per business). Add a new row when a provider changes a price; the row with
    the latest ``effective_from`` on or before the day is used. ``rate`` is a decimal string, USD."""

    __tablename__ = "price_records"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    item: Mapped[str] = mapped_column(String)  # elevenlabs_stt_usd_per_hour | elevenlabs_tts_usd_per_1k_chars | openai:<model>:input_usd_per_mtok | openai:<model>:output_usd_per_mtok
    rate: Mapped[str] = mapped_column(String)
    effective_from: Mapped[Any] = mapped_column(Date)
    source_note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[UUID | None] = mapped_column(Uuid, default=None)  # platform admin user id (no foreign key: survives account deletion)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ---- Internal project tracker (platform-level, NOT tenant data: no business_id, only listed platform admins can reach it) ----

class ProjectTask(Base):
    __tablename__ = "project_tasks"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    key: Mapped[str | None] = mapped_column(String, unique=True, default=None)  # stable id used by the seed script
    module: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="not_started")
    priority: Mapped[str] = mapped_column(String, default="medium")
    weight: Mapped[int] = mapped_column(Integer, default=1)
    start_date: Mapped[Any] = mapped_column(Date, default=None, nullable=True)
    deadline: Mapped[Any] = mapped_column(Date, default=None, nullable=True)
    blocker: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    depends_on: Mapped[Any] = mapped_column(Json, default=list)
    evidence_kind: Mapped[str | None] = mapped_column(String, default=None)
    evidence: Mapped[str] = mapped_column(Text, default="")
    is_launch: Mapped[bool] = mapped_column(Boolean, default=False)
    launch_area: Mapped[str | None] = mapped_column(String, default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    updated_by: Mapped[UUID | None] = mapped_column(Uuid, default=None)


class ProjectMilestone(Base):
    __tablename__ = "project_milestones"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(Text)
    phase: Mapped[str] = mapped_column(String, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    start_date: Mapped[Any] = mapped_column(Date, default=None, nullable=True)
    target_date: Mapped[Any] = mapped_column(Date)
    reached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class ProjectExternal(Base):
    __tablename__ = "project_external"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String)  # awaiting_us | awaiting_provider | awaiting_approval | completed
    owner: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class ProjectFinance(Base):
    __tablename__ = "project_finance"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    label: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String)  # api | telephony | email | hosting | other
    kind: Mapped[str] = mapped_column(String)  # estimate | actual | commitment
    amount_micro_usd: Mapped[int] = mapped_column(BigInteger, default=0)
    period: Mapped[str] = mapped_column(String, default="")  # free text such as "2026-11" or "per month"
    state: Mapped[str] = mapped_column(String, default="")  # commitments: outstanding | settled
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ProjectTestRun(Base):
    __tablename__ = "project_test_runs"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    source: Mapped[str] = mapped_column(String, default="pytest")
    commit: Mapped[str] = mapped_column(String, default="")
    total: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    duration_s: Mapped[float] = mapped_column(Float, default=0)
    coverage_pct: Mapped[float | None] = mapped_column(Float, default=None)
    checks: Mapped[Any] = mapped_column(Json, default=dict)  # {"tsc": true, "lint": true, "build": false}; absent = not run
    by_module: Mapped[Any] = mapped_column(Json, default=dict)
    failures: Mapped[Any] = mapped_column(Json, default=list)  # names of failing tests, no output text
