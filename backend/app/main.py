from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1 import auth, cases, customers, dashboard, knowledge, organization, privacy, team, usage, voice
from app.api.v1 import settings as settings_api
from app.core.config import Settings, get_settings
from app.core.security import RateLimiter
from app.database.connection import make_engine, make_session_factory
from app.services.email import EmailService, build_email_service
from app.services.voice.stack import VoiceStack, build_voice_stack

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def create_app(settings: Settings | None = None, session_factory: async_sessionmaker[AsyncSession] | None = None,
               voice_stack: VoiceStack | None = None, email_service: EmailService | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="AI Business Platform API", docs_url=None if settings.environment == "production" else "/docs")
    app.state.settings = settings
    app.state.auth_limiter = RateLimiter(settings.auth_rate_limit_attempts, settings.auth_rate_limit_window_seconds)
    if session_factory is None:
        session_factory = make_session_factory(make_engine(settings))
    app.state.session_factory = session_factory
    app.state.email = email_service if email_service is not None else build_email_service(settings)
    # Live voice stays off (None) unless explicitly enabled and both provider keys are configured.
    app.state.voice_stack = voice_stack if voice_stack is not None else build_voice_stack(settings, session_factory)

    allowed = set(settings.cors_origins)

    @app.middleware("http")
    async def origin_check(request: Request, call_next):
        """Cross-site request forgery guard for cookie sessions: every state-changing request
        must come from a configured origin (browsers always send Origin on such requests)."""
        if request.method in UNSAFE:
            origin = request.headers.get("origin")
            if origin is None and request.headers.get("referer"):
                parts = urlsplit(request.headers["referer"])
                origin = f"{parts.scheme}://{parts.netloc}"
            if origin not in allowed:
                return JSONResponse({"detail": "Request origin not allowed"}, status_code=403)
        return await call_next(request)

    # Added after the origin check so CORS headers are also applied to its refusals.
    app.add_middleware(
        CORSMiddleware, allow_origins=list(allowed), allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Content-Type", "X-Business-Id"],
    )

    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(dashboard.router, prefix="/api/v1")
    app.include_router(customers.router, prefix="/api/v1")
    app.include_router(cases.router, prefix="/api/v1")
    app.include_router(organization.departments, prefix="/api/v1")
    app.include_router(organization.employees, prefix="/api/v1")
    app.include_router(knowledge.router, prefix="/api/v1")
    app.include_router(team.router, prefix="/api/v1")
    app.include_router(team.public, prefix="/api/v1")
    app.include_router(privacy.router, prefix="/api/v1")
    app.include_router(usage.router, prefix="/api/v1")
    app.include_router(usage.platform, prefix="/api/v1")
    app.include_router(voice.router, prefix="/api/v1")
    app.include_router(settings_api.router, prefix="/api/v1")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
