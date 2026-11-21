"""Per-business AI privacy controls and the audit log. Everything is scoped to the caller's business."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import Principal, get_db, require
from app.database.models import AuditEvent, BusinessPrivacy, User
from app.services import audit

router = APIRouter(tags=["privacy"])


async def load_privacy(db: AsyncSession, business_id) -> BusinessPrivacy | None:
    return (await db.execute(select(BusinessPrivacy).where(BusinessPrivacy.business_id == business_id))).scalar_one_or_none()


def _out(row: BusinessPrivacy | None, settings) -> dict:
    return {
        "ai_providers_enabled": True if row is None else row.ai_providers_enabled,
        "redact_contact_details": settings.voice_redact_contact_details if row is None else row.redact_contact_details,
        # Always on at the platform level; shown so the screen can say what is protected.
        "redact_secrets": settings.voice_redact_secrets,
        "updated_at": row.updated_at.isoformat() if row else None,
    }


class PrivacyIn(BaseModel):
    ai_providers_enabled: bool | None = None
    redact_contact_details: bool | None = None


@router.get("/privacy")
async def read_privacy(request: Request, p: Principal = Depends(require("privacy:read")), db: AsyncSession = Depends(get_db)):
    return _out(await load_privacy(db, p.business_id), request.app.state.settings)


@router.patch("/privacy")
async def update_privacy(body: PrivacyIn, request: Request, p: Principal = Depends(require("privacy:write")),
                         db: AsyncSession = Depends(get_db)):
    settings = request.app.state.settings
    row = await load_privacy(db, p.business_id)
    current = _out(row, settings)
    if row is None:
        row = BusinessPrivacy(business_id=p.business_id, ai_providers_enabled=current["ai_providers_enabled"],
                              redact_contact_details=current["redact_contact_details"])
        db.add(row)
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None and v != current[k]}
    for key, value in changes.items():
        setattr(row, key, value)
    if changes:
        row.updated_by = p.user.id
        audit.record(db, p.business_id, p.user.id, "privacy.updated", changed=changes)
    await db.commit()
    return _out(row, settings)


@router.get("/audit")
async def list_audit(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                     p: Principal = Depends(require("audit:read")), db: AsyncSession = Depends(get_db)):
    where = AuditEvent.business_id == p.business_id
    total = (await db.execute(select(func.count()).select_from(AuditEvent).where(where))).scalar_one()
    rows = (await db.execute(select(AuditEvent, User.full_name).outerjoin(User, User.id == AuditEvent.actor_user_id)
                             .where(where).order_by(AuditEvent.created_at.desc(), AuditEvent.id)
                             .limit(page_size).offset((page - 1) * page_size))).all()
    items = [{"id": str(e.id), "action": e.action, "actor_name": name, "detail": e.detail, "created_at": e.created_at.isoformat()} for e, name in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}
