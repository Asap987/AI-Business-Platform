from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import Principal, current_principal, get_db, get_settings_dep
from app.core.config import Settings
from app.core.security import hash_password, new_session_token, token_digest, verify_password
from app.database.models import AuthSession, Business, EmailVerification, PasswordReset, Role, User
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"  # shape check only; deliverability is not verified

DEFAULT_ROLES = {
    "Administrator": ["*"],
    "Manager": ["cases:write", "customers:write", "departments:write", "employees:write", "knowledge:write", "reports:read"],
    "Employee": ["cases:write", "customers:write", "departments:read", "employees:read", "knowledge:read"],
}


class LoginBody(BaseModel):
    email: str = Field(max_length=254, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=1, max_length=256)


class RegisterBody(BaseModel):
    business_name: str = Field(min_length=2, max_length=120)
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=254, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=10, max_length=256)


class ForgotBody(BaseModel):
    email: str = Field(max_length=254, pattern=EMAIL_PATTERN)


class ResetBody(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=10, max_length=256)


def _session_response(p: Principal, email_on: bool = False) -> dict:
    return {
        "user": {
            "id": str(p.user.id), "email": p.user.email, "full_name": p.user.full_name, "status": p.user.status,
            "email_verified": p.user.email_verified_at is not None,
            # True only when email is switched on and this address is not yet proven; the app shows a banner then.
            "email_verification_required": email_on and p.user.email_verified_at is None,
            "role": {"id": str(p.role.id), "name": p.role.name,
                     "permissions": list(p.role.permissions) if isinstance(p.role.permissions, list) else []},
        },
        "business": {"id": str(p.business.id), "name": p.business.name, "slug": p.business.slug},
    }


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _limit(request: Request, scope: str, extra: str = "") -> None:
    if not request.app.state.auth_limiter.hit(f"{scope}:{_client(request)}:{extra}"):
        raise HTTPException(429, "Too many attempts. Please wait and try again.")


async def _start_session(db: AsyncSession, user: User, business_id, response: Response, settings: Settings) -> str:
    token = new_session_token()
    ttl = timedelta(hours=settings.session_ttl_hours)
    db.add(AuthSession(user_id=user.id, business_id=business_id, token_hash=token_digest(token),
                       expires_at=datetime.now(timezone.utc) + ttl))
    response.set_cookie(
        settings.session_cookie_name, token, max_age=int(ttl.total_seconds()), httponly=True,
        secure=settings.environment == "production", samesite="lax", path="/",
    )
    return token


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "business"


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response, db: AsyncSession = Depends(get_db),
                settings: Settings = Depends(get_settings_dep)):
    _limit(request, "login", body.email.lower())
    user = (await db.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    ok = verify_password(body.password, user.password_hash if user else None)
    business = await db.get(Business, user.business_id) if user else None
    if not (ok and user and user.status == "active" and business and business.status == "active"):
        raise HTTPException(401, "Incorrect email or password")  # same answer for every failure
    user.last_login_at = datetime.now(timezone.utc)
    await _start_session(db, user, business.id, response, settings)
    await db.commit()
    role = await db.get(Role, user.role_id)
    return _session_response(Principal(user=user, role=role, business=business, session=None), request.app.state.email.enabled)  # type: ignore[arg-type]


@router.post("/register", status_code=201)
async def register(body: RegisterBody, request: Request, response: Response, tasks: BackgroundTasks, db: AsyncSession = Depends(get_db),
                   settings: Settings = Depends(get_settings_dep)):
    _limit(request, "register")
    email = body.email.lower()
    if (await db.execute(select(func.count()).select_from(User).where(User.email == email))).scalar_one():
        raise HTTPException(409, "An account with this email already exists")
    base = _slugify(body.business_name)
    slug, n = base, 1
    while (await db.execute(select(func.count()).select_from(Business).where(Business.slug == slug))).scalar_one():
        n += 1
        slug = f"{base}-{n}"
    business = Business(name=body.business_name.strip(), slug=slug)
    db.add(business)
    await db.flush()
    roles = {name: Role(business_id=business.id, name=name, permissions=perms) for name, perms in DEFAULT_ROLES.items()}
    db.add_all(roles.values())
    await db.flush()
    user = User(business_id=business.id, role_id=roles["Administrator"].id, email=email,
                password_hash=hash_password(body.password), full_name=body.full_name.strip(),
                last_login_at=datetime.now(timezone.utc))
    db.add(user)
    await db.flush()
    await _start_session(db, user, business.id, response, settings)
    email = request.app.state.email
    token = await _issue_verification(db, user, settings) if email.enabled else None
    await db.commit()
    if token:
        tasks.add_task(email.send_verification, user.email, token, settings.email_verification_hours)
    return _session_response(Principal(user=user, role=roles["Administrator"], business=business, session=None), email.enabled)  # type: ignore[arg-type]


async def _issue_verification(db: AsyncSession, user: User, settings: Settings) -> str:
    await db.execute(delete(EmailVerification).where(EmailVerification.user_id == user.id, EmailVerification.used_at.is_(None)))
    token = new_session_token()
    db.add(EmailVerification(user_id=user.id, token_hash=token_digest(token),
                             expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.email_verification_hours)))
    return token


class VerifyBody(BaseModel):
    token: str = Field(min_length=20, max_length=200)


@router.post("/verify-email", status_code=204)
async def verify_email(body: VerifyBody, request: Request, db: AsyncSession = Depends(get_db)):
    _limit(request, "verify")
    row = (await db.execute(select(EmailVerification).where(EmailVerification.token_hash == token_digest(body.token)))).scalar_one_or_none()
    expires = (row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)) if row else None
    user = await db.get(User, row.user_id) if row else None
    if not (row and row.used_at is None and expires > datetime.now(timezone.utc) and user):
        raise HTTPException(404, "This confirmation link is invalid or has expired. Sign in and ask for a new one.")
    now = datetime.now(timezone.utc)
    row.used_at = now
    if user.email_verified_at is None:
        user.email_verified_at = now
    audit.record(db, user.business_id, user.id, "email.verified")
    await db.commit()
    return Response(status_code=204)


@router.post("/resend-verification", status_code=204)
async def resend_verification(request: Request, tasks: BackgroundTasks, p: Principal = Depends(current_principal),
                              db: AsyncSession = Depends(get_db), settings: Settings = Depends(get_settings_dep)):
    email = request.app.state.email
    if not email.enabled:
        raise HTTPException(503, "Email is not set up on this system yet, so a confirmation email cannot be sent.")
    _limit(request, "resend-verify", str(p.user.id))
    if p.user.email_verified_at is None:
        token = await _issue_verification(db, p.user, settings)
        await db.commit()
        tasks.add_task(email.send_verification, p.user.email, token, settings.email_verification_hours)
    return Response(status_code=204, background=tasks)


@router.post("/logout", status_code=204)
async def logout(request: Request, db: AsyncSession = Depends(get_db), settings: Settings = Depends(get_settings_dep)):
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        row = (await db.execute(select(AuthSession).where(AuthSession.token_hash == token_digest(token)))).scalar_one_or_none()
        if row:
            await db.delete(row)
            await db.commit()
    resp = Response(status_code=204)
    resp.delete_cookie(settings.session_cookie_name, path="/")
    return resp


@router.get("/me")
async def me(request: Request, principal: Principal = Depends(current_principal)):
    return _session_response(principal, request.app.state.email.enabled)


@router.post("/forgot-password", status_code=204)
async def forgot_password(body: ForgotBody, request: Request, tasks: BackgroundTasks, db: AsyncSession = Depends(get_db),
                          settings: Settings = Depends(get_settings_dep)):
    """Always answers 204, whether or not the account exists, and the email goes out after the answer, so neither
    the response nor its timing can be used to find accounts."""
    _limit(request, "forgot", body.email.lower())
    user = (await db.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    business = await db.get(Business, user.business_id) if user else None
    if user and user.status == "active" and business and business.status == "active":
        await db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None)))
        token = new_session_token()
        db.add(PasswordReset(user_id=user.id, token_hash=token_digest(token),
                             expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.password_reset_minutes)))
        audit.record(db, user.business_id, user.id, "password.reset_requested")
        await db.commit()
        tasks.add_task(request.app.state.email.send_password_reset, user.email, token, settings.password_reset_minutes)
    return Response(status_code=204, background=tasks)


@router.post("/reset-password", status_code=204)
async def reset_password(body: ResetBody, request: Request, tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    _limit(request, "reset")
    row = (await db.execute(select(PasswordReset).where(PasswordReset.token_hash == token_digest(body.token)))).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    expires = row.expires_at.replace(tzinfo=timezone.utc) if row and row.expires_at.tzinfo is None else (row.expires_at if row else None)
    user = await db.get(User, row.user_id) if row else None
    if not (row and row.used_at is None and expires > now and user and user.status == "active"):
        raise HTTPException(404, "This reset link is invalid or has expired. Please request a new one.")
    user.password_hash = hash_password(body.password)
    row.used_at = now
    await db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))  # sign out everywhere
    await db.execute(update(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None)).values(used_at=now))
    audit.record(db, user.business_id, user.id, "password.reset_completed")
    await db.commit()
    tasks.add_task(request.app.state.email.send_password_changed_notice, user.email)
    return Response(status_code=204, background=tasks)
