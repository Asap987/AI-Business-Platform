"""Organisation profile: what a business is, where, when it is open, its policies and how its assistants should speak.

Tenant isolation: the business always comes from the signed-in Principal. There is no id in any URL or body
(extra="forbid"). Anyone signed in may read their own organisation's profile; changing it needs business:write.
Nothing here is shared across businesses or exposed to platform-wide views.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import _session_response
from app.api.v1.deps import Principal, current_principal, get_db, require
from app.database.models.tables import Business, BusinessProfile
from app.services import audit
from app.services.telephony.schedule import valid_timezone, validate_hours

router = APIRouter(tags=["business-profile"])

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^\+?[0-9 ()\-]{5,24}$")


def _clean(v: str | None, limit: int) -> str | None:
    if v is None:
        return None
    v = v.strip()
    if len(v) > limit:
        raise ValueError(f"must be at most {limit} characters")
    return v or None


def _phone(v: str | None) -> str | None:
    v = _clean(v, 24)
    if v is not None and not _PHONE.match(v):
        raise ValueError("is not a valid phone number")
    return v


class Branch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    address: str | None = Field(default=None, max_length=300)
    phone: str | None = None

    @field_validator("name")
    @classmethod
    def _n(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name is required")
        return v

    @field_validator("address")
    @classmethod
    def _a(cls, v): return _clean(v, 300)

    @field_validator("phone")
    @classmethod
    def _p(cls, v): return _phone(v)


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("title", "text")
    @classmethod
    def _t(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be empty")
        return v


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    greeting: str | None = Field(default=None, max_length=300)
    tone: str | None = Field(default=None, pattern="^(friendly|professional|formal)$")
    after_hours_message: str | None = Field(default=None, max_length=500)
    escalation_note: str | None = Field(default=None, max_length=500)

    @field_validator("greeting", "after_hours_message", "escalation_note")
    @classmethod
    def _s(cls, v): return _clean(v, 500)


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=120)
    industry: str | None = Field(default=None, max_length=80)
    country: str | None = Field(default=None, max_length=80)
    timezone: str = Field(default="UTC", max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    contact_phone: str | None = None
    contact_email: str | None = None
    website: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=300)
    branches: list[Branch] = Field(default_factory=list, max_length=20)
    hours: dict[str, Any] | None = None
    policies: list[Policy] = Field(default_factory=list, max_length=30)
    languages: list[str] = Field(default_factory=list, max_length=12)
    preferences: Preferences = Field(default_factory=Preferences)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("name must be at least 2 characters")
        return v

    @field_validator("industry", "country")
    @classmethod
    def _short(cls, v): return _clean(v, 80)

    @field_validator("description")
    @classmethod
    def _desc(cls, v): return _clean(v, 2000)

    @field_validator("address")
    @classmethod
    def _addr(cls, v): return _clean(v, 300)

    @field_validator("contact_phone")
    @classmethod
    def _cp(cls, v): return _phone(v)

    @field_validator("contact_email")
    @classmethod
    def _ce(cls, v):
        v = _clean(v, 200)
        if v is not None and not _EMAIL.match(v):
            raise ValueError("is not a valid email address")
        return v.lower() if v else None

    @field_validator("website")
    @classmethod
    def _site(cls, v):
        v = _clean(v, 200)
        if v is not None and not re.match(r"^https?://[^\s/]+\.[^\s]+$", v):
            raise ValueError("must start with http:// or https://")
        return v

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        if not valid_timezone(v):
            raise ValueError("is not a known time zone")
        return v

    @field_validator("hours")
    @classmethod
    def _hours(cls, v):
        problem = validate_hours(v)
        if problem:
            raise ValueError(problem)
        return v

    @field_validator("languages")
    @classmethod
    def _langs(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for item in v:
            item = item.strip()
            if not item or len(item) > 40:
                raise ValueError("each language must be 1 to 40 characters")
            if item.lower() not in {x.lower() for x in out}:
                out.append(item)
        return out


def _view(business: Business, p: BusinessProfile | None) -> dict[str, Any]:
    return {
        "name": business.name, "industry": business.industry, "country": business.country, "timezone": business.timezone,
        "description": p.description if p else None,
        "contact_phone": p.contact_phone if p else None,
        "contact_email": p.contact_email if p else None,
        "website": p.website if p else None,
        "address": p.address if p else None,
        "branches": (p.branches if p else None) or [],
        "hours": p.hours if p else None,
        "policies": (p.policies if p else None) or [],
        "languages": (p.languages if p else None) or [],
        "preferences": (p.preferences if p else None) or {},
    }


async def _load(db: AsyncSession, business_id) -> tuple[Business, BusinessProfile | None]:
    business = (await db.execute(select(Business).where(Business.id == business_id))).scalar_one_or_none()
    if business is None:
        raise HTTPException(404, "Not found")
    profile = (await db.execute(select(BusinessProfile).where(BusinessProfile.business_id == business_id))).scalar_one_or_none()
    return business, profile


@router.get("/business/profile")
async def get_profile(principal: Principal = Depends(current_principal), db: AsyncSession = Depends(get_db)):
    business, profile = await _load(db, principal.business_id)
    return _view(business, profile)


@router.put("/business/profile")
async def put_profile(
    payload: ProfileIn,
    request: Request,
    principal: Principal = Depends(require("business:write")),
    db: AsyncSession = Depends(get_db),
):
    business, profile = await _load(db, principal.business_id)
    before = _view(business, profile)
    if profile is None:
        profile = BusinessProfile(business_id=principal.business_id)
        db.add(profile)
    business.name, business.industry, business.country, business.timezone = payload.name, payload.industry, payload.country, payload.timezone
    profile.description, profile.contact_phone, profile.contact_email = payload.description, payload.contact_phone, payload.contact_email
    profile.website, profile.address = payload.website, payload.address
    profile.branches = [b.model_dump() for b in payload.branches]
    profile.hours = payload.hours
    profile.policies = [x.model_dump() for x in payload.policies]
    profile.languages = payload.languages
    profile.preferences = {k: v for k, v in payload.preferences.model_dump().items() if v}
    after = _view(business, profile)
    # Field names only: the values (contact details, policies) never go into the audit trail.
    changed = sorted(k for k in after if after[k] != before[k])
    audit.record(db, principal.business_id, principal.user.id, "business.profile_updated", changed=changed)
    await db.commit()
    return after
