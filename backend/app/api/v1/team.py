"""Staff accounts: invitations, role changes and disabling logins. Everything is scoped to the caller's business."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import EMAIL_PATTERN, _limit, _session_response, _start_session
from app.api.v1.deps import Principal, get_db, get_settings_dep, require
from app.core.config import Settings
from app.core.security import hash_password, new_session_token, token_digest
from app.services import audit
from app.database.models import AuthSession, Business, Employee, Role, User, UserInvite

router = APIRouter(tags=["team"])
public = APIRouter(prefix="/auth", tags=["auth"])

INVITE_DAYS = 7
CANT_INVITE = "That email address can't be invited. It may already have an account or a pending invitation."


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # SQLite returns naive datetimes


def _is_admin(role: Role) -> bool:
    return isinstance(role.permissions, list) and "*" in role.permissions


def _user_out(u: User, role: Role, linked: bool) -> dict:
    return {"id": str(u.id), "email": u.email, "full_name": u.full_name, "status": u.status,
            "role": {"id": str(role.id), "name": role.name}, "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "created_at": u.created_at.isoformat(), "has_employee_profile": linked}


def _role_out(r: Role) -> dict:
    return {"id": str(r.id), "name": r.name, "description": r.description,
            "permissions": list(r.permissions) if isinstance(r.permissions, list) else []}


async def _role(db, business_id, role_id) -> Role:
    r = (await db.execute(select(Role).where(Role.id == role_id, Role.business_id == business_id))).scalar_one_or_none()
    if r is None:
        raise HTTPException(422, "Role not found")
    return r


# ---------------------------------------------------------------- read
@router.get("/roles")
async def list_roles(p: Principal = Depends(require("users:read")), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Role).where(Role.business_id == p.business_id).order_by(Role.name))).scalars().all()
    return {"items": [_role_out(r) for r in rows]}


@router.get("/users")
async def list_users(p: Principal = Depends(require("users:read")), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(User, Role).join(Role, Role.id == User.role_id).where(
        User.business_id == p.business_id, Role.business_id == p.business_id).order_by(User.full_name))).all()
    linked = set((await db.execute(select(Employee.user_id).where(
        Employee.business_id == p.business_id, Employee.user_id.is_not(None)))).scalars().all())
    return {"items": [_user_out(u, r, u.id in linked) for u, r in rows]}


@router.get("/users/invites")
async def list_invites(p: Principal = Depends(require("users:read")), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(UserInvite, Role).join(Role, Role.id == UserInvite.role_id).where(
        UserInvite.business_id == p.business_id, UserInvite.accepted_at.is_(None)).order_by(UserInvite.created_at.desc()))).all()
    now = datetime.now(timezone.utc)
    return {"items": [{"id": str(i.id), "email": i.email, "role": {"id": str(r.id), "name": r.name},
                       "created_at": i.created_at.isoformat(), "expires_at": i.expires_at.isoformat(),
                       "expired": _utc(i.expires_at) <= now} for i, r in rows]}


# ---------------------------------------------------------------- invite
class InviteIn(BaseModel):
    email: str = Field(max_length=254, pattern=EMAIL_PATTERN)
    role_id: UUID
    employee_id: UUID | None = None

    @field_validator("email", mode="before")
    @classmethod
    def _norm(cls, v):
        return v.strip().lower() if isinstance(v, str) else v


@router.post("/users/invites", status_code=201)
async def create_invite(body: InviteIn, p: Principal = Depends(require("users:write")), db: AsyncSession = Depends(get_db)):
    await _role(db, p.business_id, body.role_id)
    if body.employee_id is not None:
        emp = (await db.execute(select(Employee).where(Employee.id == body.employee_id, Employee.business_id == p.business_id))).scalar_one_or_none()
        if emp is None:
            raise HTTPException(422, "Employee not found")
        if emp.user_id is not None:
            raise HTTPException(409, "That employee already has a login")
    taken = (await db.execute(select(func.count()).select_from(User).where(User.email == body.email))).scalar_one()
    pending = (await db.execute(select(UserInvite).where(
        UserInvite.business_id == p.business_id, UserInvite.email == body.email, UserInvite.accepted_at.is_(None)))).scalar_one_or_none()
    if pending is not None and _utc(pending.expires_at) <= datetime.now(timezone.utc):
        await db.delete(pending)  # an expired invitation may be replaced
        await db.flush()
        pending = None
    if taken or pending is not None:
        raise HTTPException(409, CANT_INVITE)  # one answer, so another business's accounts are not revealed
    token = new_session_token()
    inv = UserInvite(business_id=p.business_id, email=body.email, role_id=body.role_id, employee_id=body.employee_id,
                     token_hash=token_digest(token), invited_by=p.user.id,
                     expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_DAYS))
    db.add(inv)
    await db.flush()
    audit.record(db, p.business_id, p.user.id, "invite.created", invite_id=inv.id, email=body.email, role_id=body.role_id)
    await db.commit()
    # The token is returned this once and never again; only its hash is stored.
    return {"id": str(inv.id), "email": inv.email, "token": token, "expires_at": inv.expires_at.isoformat()}


@router.delete("/users/invites/{invite_id}", status_code=204)
async def revoke_invite(invite_id: UUID, p: Principal = Depends(require("users:write")), db: AsyncSession = Depends(get_db)):
    res = await db.execute(delete(UserInvite).where(
        UserInvite.id == invite_id, UserInvite.business_id == p.business_id, UserInvite.accepted_at.is_(None)))
    if res.rowcount == 0:
        raise HTTPException(404, "Invitation not found")
    audit.record(db, p.business_id, p.user.id, "invite.revoked", invite_id=invite_id)
    await db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- change a user
class UserPatch(BaseModel):
    role_id: UUID | None = None
    status: Literal["active", "disabled"] | None = None


@router.patch("/users/{user_id}")
async def update_user(user_id: UUID, body: UserPatch, p: Principal = Depends(require("users:write")), db: AsyncSession = Depends(get_db)):
    u = (await db.execute(select(User).where(User.id == user_id, User.business_id == p.business_id))).scalar_one_or_none()
    if u is None:
        raise HTTPException(404, "User not found")
    changes = body.model_dump(exclude_unset=True)
    if "role_id" in changes and body.role_id is None or "status" in changes and body.status is None:
        raise HTTPException(422, "Value cannot be empty")
    role = await db.get(Role, u.role_id)
    new_role = await _role(db, p.business_id, body.role_id) if body.role_id else role
    new_status = body.status or u.status
    if u.status == "invited" and "status" in changes:
        raise HTTPException(409, "This user has not accepted their invitation")
    if u.id == p.user.id and (new_role.id != role.id or new_status != "active"):
        raise HTTPException(409, "You cannot change your own role or disable your own account")
    losing_admin = u.status == "active" and _is_admin(role) and (not _is_admin(new_role) or new_status != "active")
    if losing_admin:
        admins = (await db.execute(select(User, Role).join(Role, Role.id == User.role_id).where(
            User.business_id == p.business_id, User.status == "active"))).all()
        if sum(1 for _, r in admins if _is_admin(r)) <= 1:
            raise HTTPException(409, "At least one active administrator must remain")
    audit.record(db, p.business_id, p.user.id, "user.updated", user_id=u.id,
                 **({"role": f"{role.name} -> {new_role.name}"} if new_role.id != role.id else {}),
                 **({"status": f"{u.status} -> {new_status}"} if new_status != u.status else {}))
    u.role_id, u.status = new_role.id, new_status
    if new_status != "active":
        await db.execute(delete(AuthSession).where(AuthSession.user_id == u.id))  # sign them out everywhere now
    await db.commit()
    linked = (await db.execute(select(func.count()).select_from(Employee).where(
        Employee.user_id == u.id, Employee.business_id == p.business_id))).scalar_one() > 0
    return _user_out(u, new_role, linked)


# ---------------------------------------------------------------- public: accept an invitation
class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class AcceptIn(TokenIn):
    password: str = Field(min_length=10, max_length=256)
    full_name: str | None = Field(default=None, min_length=2, max_length=120)


async def _valid_invite(db, token: str) -> UserInvite:
    inv = (await db.execute(select(UserInvite).where(UserInvite.token_hash == token_digest(token)))).scalar_one_or_none()
    if inv is None or inv.accepted_at is not None or _utc(inv.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(404, "This invitation is invalid or has expired")  # same answer for every failure
    return inv


@public.post("/invite-info")
async def invite_info(body: TokenIn, request: Request, db: AsyncSession = Depends(get_db)):
    _limit(request, "invite")
    inv = await _valid_invite(db, body.token)
    business = await db.get(Business, inv.business_id)
    role = await db.get(Role, inv.role_id)
    emp = await db.get(Employee, inv.employee_id) if inv.employee_id else None
    return {"email": inv.email, "business_name": business.name, "role_name": role.name,
            "suggested_name": emp.full_name if emp else None}


@public.post("/accept-invite", status_code=201)
async def accept_invite(body: AcceptIn, request: Request, response: Response, db: AsyncSession = Depends(get_db),
                        settings: Settings = Depends(get_settings_dep)):
    _limit(request, "invite")
    inv = await _valid_invite(db, body.token)
    business = await db.get(Business, inv.business_id)
    role = await db.get(Role, inv.role_id)
    emp = await db.get(Employee, inv.employee_id) if inv.employee_id else None
    name = (body.full_name or (emp.full_name if emp else "")).strip()
    if len(name) < 2:
        raise HTTPException(422, "Please enter your name")
    if business.status != "active":
        raise HTTPException(404, "This invitation is invalid or has expired")
    if (await db.execute(select(func.count()).select_from(User).where(User.email == inv.email))).scalar_one():
        raise HTTPException(409, "An account with this email already exists")
    user = User(business_id=inv.business_id, role_id=role.id, email=inv.email, password_hash=hash_password(body.password),
                full_name=name, last_login_at=datetime.now(timezone.utc))
    db.add(user)
    await db.flush()
    if emp is not None and emp.user_id is None and emp.business_id == inv.business_id:
        emp.user_id = user.id
    inv.accepted_at = datetime.now(timezone.utc)
    audit.record(db, inv.business_id, user.id, "invite.accepted", invite_id=inv.id, user_id=user.id)
    await _start_session(db, user, business.id, response, settings)
    await db.commit()
    return _session_response(Principal(user=user, role=role, business=business, session=None))  # type: ignore[arg-type]
