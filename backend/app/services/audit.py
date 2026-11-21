"""Audit log of sensitive changes. Call before ``commit`` so the entry and the change succeed or fail together."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AuditEvent


def record(db: AsyncSession, business_id: UUID, actor_user_id: UUID | None, action: str, **detail: Any) -> None:
    """``detail`` is for field names, ids and flags. Never put message text, passwords or tokens in it."""
    db.add(AuditEvent(business_id=business_id, actor_user_id=actor_user_id, action=action,
                      detail={k: (str(v) if isinstance(v, UUID) else v) for k, v in detail.items()}))
