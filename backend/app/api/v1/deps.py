"""Request-scoped dependencies: database session, authenticated user and tenant."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import token_digest
from app.database.models import AuthSession, Business, Role, User


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


@dataclass
class Principal:
    user: User
    role: Role
    business: Business
    session: AuthSession

    @property
    def business_id(self) -> UUID:
        """The ONLY business any query for this request may touch."""
        return self.business.id


async def current_principal(
    request: Request, db: AsyncSession = Depends(get_db), settings: Settings = Depends(get_settings_dep)
) -> Principal:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(401, "Not authenticated")
    row = (await db.execute(select(AuthSession).where(AuthSession.token_hash == token_digest(token)))).scalar_one_or_none()
    expires = row.expires_at if row else None
    if expires is not None and expires.tzinfo is None:  # SQLite returns naive datetimes
        expires = expires.replace(tzinfo=timezone.utc)
    if row is None or expires <= datetime.now(timezone.utc):
        raise HTTPException(401, "Not authenticated")
    user = await db.get(User, row.user_id)
    business = await db.get(Business, row.business_id)
    if user is None or business is None or user.status != "active" or business.status != "active":
        raise HTTPException(401, "Not authenticated")
    # The session is bound to one business. A different X-Business-Id is refused, never honoured.
    requested = request.headers.get("x-business-id")
    if requested and requested.lower() != str(business.id):
        raise HTTPException(403, "You do not have access to that business")
    role = await db.get(Role, user.role_id)
    return Principal(user=user, role=role, business=business, session=row)


def has_permission(role: Role, needed: str) -> bool:
    """Roles hold strings like "cases:write". "*" grants everything; "x:write" also grants "x:read"."""
    held = role.permissions if isinstance(role.permissions, list) else []
    if "*" in held or needed in held:
        return True
    resource, _, action = needed.partition(":")
    return action == "read" and f"{resource}:write" in held


def require(permission: str):
    async def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if not has_permission(principal.role, permission):
            raise HTTPException(403, "You do not have permission to do that")
        return principal

    return dependency
