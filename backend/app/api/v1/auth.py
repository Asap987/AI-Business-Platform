from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import Principal, current_principal, get_db, get_settings_dep
from app.core.config import Settings
from app.core.security import hash_password, new_session_token, token_digest, verify_password
from app.database.models import AuthSession, Business, Role, User

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"  # shape check only; deliverability is not verified

DEFAULT_ROLES = {
    "Administrator": ["*"],
    "Manager": ["cases:write", "customers:write", "reports:read"],
    "Employee": ["cases:write", "customers:write"],
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


def _session_response(p: Principal) -> dict:
    return {
        "user": {
            "id": str(p.user.id), "email": p.user.email, "full_name": p.user.full_name, "status": p.user.status,
            "role": {"id": str(p.role.id), "name": p.role.name},
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
    return _session_response(Principal(user=user, role=role, business=business, session=None))  # type: ignore[arg-type]


@router.post("/register", status_code=201)
async def register(body: RegisterBody, request: Request, response: Response, db: AsyncSession = Depends(get_db),
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
    await db.commit()
    return _session_response(Principal(user=user, role=roles["Administrator"], business=business, session=None))  # type: ignore[arg-type]


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
async def me(principal: Principal = Depends(current_principal)):
    return _session_response(principal)


@router.post("/forgot-password", status_code=204)
async def forgot_password(body: ForgotBody, request: Request):
    # No token table or email provider exists yet, so nothing is sent. The answer is the same
    # whether or not the account exists, so this endpoint cannot be used to find accounts.
    _limit(request, "forgot", body.email.lower())
    return Response(status_code=204)
