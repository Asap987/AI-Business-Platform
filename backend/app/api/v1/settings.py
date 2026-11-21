"""Settings endpoints: profile (own name) and business (organisation name).

TASK C. See the brief for the exact contract.

Tenant isolation: business_id ALWAYS comes from the Principal, never from the
request body or URL. PATCH /profile updates only the caller's own user row.
PATCH /business updates only the caller's business. There is no id parameter
in either endpoint — a body containing "id" or "business_id" is rejected by
Pydantic's `extra="forbid"` (422).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import _session_response
from app.api.v1.deps import Principal, current_principal, get_db, require
from app.database.models.tables import Business, User
from app.services import audit


router = APIRouter(tags=["settings"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=2, max_length=120)

    @field_validator("full_name")
    @classmethod
    def _trim(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("full_name must be at least 2 characters after trimming")
        if len(v) > 120:
            raise ValueError("full_name must be at most 120 characters")
        return v


class BusinessUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)

    @field_validator("name")
    @classmethod
    def _trim(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("name must be at least 2 characters after trimming")
        if len(v) > 120:
            raise ValueError("name must be at most 120 characters")
        return v


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.patch("/profile")
async def update_profile(
    payload: ProfileUpdate,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_db),
):
    """Update ONLY the signed-in user's own name. No id parameter exists."""
    result = await db.execute(select(User).where(User.id == principal.user.id))
    user = result.scalar_one_or_none()
    if user is None:
        # Should be impossible for a signed-in principal, but do not leak.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    user.full_name = payload.full_name
    await db.commit()
    await db.refresh(user)

    return _session_response(principal)


@router.patch("/business")
async def update_business(
    payload: BusinessUpdate,
    principal: Principal = Depends(require("business:write")),
    db: AsyncSession = Depends(get_db),
):
    """Rename the signed-in user's business. Slug is not changed."""
    result = await db.execute(select(Business).where(Business.id == principal.business_id))
    business = result.scalar_one_or_none()
    if business is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    business.name = payload.name

    audit.record(
        db,
        principal.business_id,
        principal.user.id,
        "business.updated",
        changed=["name"],
    )

    await db.commit()
    await db.refresh(business)

    return _session_response(principal)