"""
ORM mapping of migrations/0001_initial.sql and 0002. The SQL files are the
source of truth for production; these models must match them. Types are
portable so the same code runs on PostgreSQL and on SQLite in quick tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
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


class Department(_Stamped, Base):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("business_id", "name"),)
    business_id: Mapped[UUID] = _fk("businesses")
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, default=None)


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
