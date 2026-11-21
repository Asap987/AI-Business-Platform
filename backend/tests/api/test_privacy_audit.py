import asyncio
import os

import pytest
from sqlalchemy import select, text

from app.core.config import Settings
from app.database.models import AuditEvent, BusinessPrivacy
from app.services.voice.interfaces.reasoning import ReasoningRequest
from app.services.voice.providers.openai_reasoning import OpenAIReasoning
from app.services.voice.language_manager import LanguageManager
from tests.api.test_customers_cases import add_user, login, two
from tests.api.test_team import accept, invite, roles
from tests.api.test_voice_call import FakeSTT, FakeWS, call, enable, settle
from app.api.v1.voice import test_call as voice_test_call
from uuid import uuid4

API = "/api/v1"


async def audit(c):
    return (await c.get(f"{API}/audit")).json()


async def test_defaults_update_and_audit_trail(env):
    a, a_id, b, b_id, factory = await two(env)
    try:
        assert (await a.get(f"{API}/privacy")).json() == {"ai_providers_enabled": True, "redact_contact_details": False,
                                                           "redact_secrets": True, "updated_at": None}
        r = await a.patch(f"{API}/privacy", json={"redact_contact_details": True})
        assert r.status_code == 200 and r.json()["redact_contact_details"] is True and r.json()["ai_providers_enabled"] is True
        assert (await a.patch(f"{API}/privacy", json={"redact_contact_details": True})).status_code == 200  # no change, no entry
        assert (await a.patch(f"{API}/privacy", json={"ai_providers_enabled": False})).json()["ai_providers_enabled"] is False
        log = await audit(a)
        assert log["total"] == 2 and [e["action"] for e in log["items"]] == ["privacy.updated"] * 2
        assert log["items"][0]["detail"] == {"changed": {"ai_providers_enabled": False}}
        assert log["items"][0]["actor_name"]  # who did it
        # the other business is untouched
        assert (await b.get(f"{API}/privacy")).json()["ai_providers_enabled"] is True
        assert (await audit(b))["total"] == 0
    finally:
        await a.aclose(), await b.aclose()


async def test_team_changes_are_audited_without_secrets(env):
    a, a_id, b, _, factory = await two(env)
    try:
        token = (await invite(a, "new@a.test")).json()["token"]
        c, _ = await accept(env, token, full_name="New Person")
        uid = {u["email"]: u["id"] for u in (await a.get(f"{API}/users")).json()["items"]}["new@a.test"]
        await a.patch(f"{API}/users/{uid}", json={"status": "disabled"})
        log = await audit(a)
        assert [e["action"] for e in log["items"]][::-1] == ["invite.created", "invite.accepted", "user.updated"]
        assert token not in str(log) and "password" not in str(log).lower()
        assert log["items"][0]["detail"]["status"] == "active -> disabled"
        await c.aclose()
    finally:
        await a.aclose(), await b.aclose()


async def test_permissions(env):
    a, a_id, b, _, factory = await two(env)
    try:
        await add_user(factory, a_id, "PrivReader", ["privacy:read"], "pr@a.test")
        await add_user(factory, a_id, "Manager2", ["cases:write"], "m@a.test")
        r, m = await login(env, "pr@a.test"), await login(env, "m@a.test")
        assert (await r.get(f"{API}/privacy")).status_code == 200
        assert (await r.patch(f"{API}/privacy", json={"ai_providers_enabled": False})).status_code == 403
        assert (await r.get(f"{API}/audit")).status_code == 403
        for path in ("privacy", "audit"):
            assert (await m.get(f"{API}/{path}")).status_code == 403
        assert (await a.get(f"{API}/privacy")).json()["ai_providers_enabled"] is True
        await r.aclose(), await m.aclose()
    finally:
        await a.aclose(), await b.aclose()


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="the append-only trigger exists in the PostgreSQL migration only")
async def test_audit_log_cannot_be_rewritten(env):
    a, a_id, b, _, factory = await two(env)
    try:
        await a.patch(f"{API}/privacy", json={"ai_providers_enabled": False})
        async with factory() as db:
            with pytest.raises(Exception, match="append-only"):
                await db.execute(text("UPDATE audit_events SET action = 'forged'"))
    finally:
        await a.aclose(), await b.aclose()


async def test_voice_refuses_when_the_business_switched_ai_off_and_carries_redaction(env):
    a, a_id, b, b_id, factory = await two(env)
    try:
        stack = enable(env, FakeSTT())
        cookie_a, cookie_b = (c.cookies.get(env[2].session_cookie_name) for c in (a, b))
        await a.patch(f"{API}/privacy", json={"ai_providers_enabled": False})
        ws = FakeWS(env[0], cookie=cookie_a); await voice_test_call(ws, None)
        assert ws.json == [{"type": "error", "code": "ai_disabled_by_business"}] and stack.store.active_count(a_id) == 0
        # B is unaffected, and B's own redaction choice reaches its session
        await b.patch(f"{API}/privacy", json={"redact_contact_details": True})
        ws2, task = await call(env, cookie_b)
        await settle(ws2, lambda: "ready" in ws2.types())
        assert [s.redact_contact_details for s in stack.store._sessions.values()] == [True]
        ws2.hang_up(); await asyncio.wait_for(task, 3)
    finally:
        await a.aclose(), await b.aclose()


def test_reasoning_request_overrides_platform_redaction():
    s = Settings(_env_file=None, voice_redact_contact_details=False)
    engine = OpenAIReasoning(s, LanguageManager(s), client=object())
    def build(flag):
        req = ReasoningRequest(business_id=uuid4(), session_id=uuid4(), language_code="en", business_context="",
                               history=[], user_text="Email me at ama@acme.test", redact_contact_details=flag)
        return engine.build_input(req)[-1]["content"]
    assert "ama@acme.test" in build(None) and "ama@acme.test" not in build(True)
    s2 = Settings(_env_file=None, voice_redact_contact_details=True)
    e2 = OpenAIReasoning(s2, LanguageManager(s2), client=object())
    req = ReasoningRequest(business_id=uuid4(), session_id=uuid4(), language_code="en", business_context="", history=[], user_text="ama@acme.test")
    assert "ama@acme.test" not in e2.build_input(req)[-1]["content"]
