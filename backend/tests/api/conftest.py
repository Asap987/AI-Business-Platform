import os

import httpx2 as httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool

from app.core.config import Settings
from app.database.models import Base
from app.main import create_app

ORIGIN = "http://localhost:3000"


@pytest.fixture
async def env():
    # TEST_DATABASE_URL (postgresql+asyncpg://...) runs the same tests against a PostgreSQL database
    # that already has migrations/0001 and 0002 applied. All its tables are emptied before each test.
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE password_resets, audit_events, business_privacy, auth_sessions, user_invites, knowledge_chunks, knowledge_documents, case_events, cases, conversations, agents, employees, departments, "
                                    "customers, users, roles, businesses CASCADE"))
    else:
        engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(_env_file=None, environment="test", auth_rate_limit_attempts=5)
    app = create_app(settings, factory)
    yield app, factory, settings
    await engine.dispose()


def make_client(app, origin=ORIGIN):
    headers = {"Origin": origin} if origin else {}
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=headers)


@pytest.fixture
async def client(env):
    async with make_client(env[0]) as c:
        yield c


REG = {"business_name": "Acme Logistics", "full_name": "Ama Mensah", "email": "ama@acme.test", "password": "a-long-passphrase"}


async def register(client, **kw):
    return await client.post("/api/v1/auth/register", json={**REG, **kw})
