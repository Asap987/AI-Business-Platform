import asyncio
import json
import logging
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from app.core.config import Settings
from app.database.models import AuditEvent, UsageSession, User
from app.services.usage_store import record_call
from app.services.voice.interfaces import ReasoningUsage, TextDelta
from app.services.voice.usage import UsageRecord
from tests.api.test_customers_cases import add_user, login, two
from tests.api.test_voice_call import CUSTOMER_WORDS, FakeSTT, call, enable, final, settle
from tests.voice.test_conversation_manager import done

API = "/api/v1"
YESTERDAY = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()


async def make_call(env, client, audio_seconds=3):
    rounds = [[TextDelta(text="We open at eight. Anything else?"), done(100, 20)]]
    keep = env[0].state.settings.platform_admin_user_ids
    enable(env, FakeSTT([final(CUSTOMER_WORDS)]), rounds)  # replaces the settings object
    env[0].state.settings.platform_admin_user_ids = keep
    ws, task = await call(env, client.cookies.get(env[2].session_cookie_name))
    await settle(ws, lambda: ws.accepted and "ready" in ws.types())
    for _ in range(audio_seconds):
        ws.client_sends(data=b"\x00\x01" * 16000)  # 32,000 bytes = 1 second of 16 kHz mono PCM16
    await settle(ws, lambda: any(m.get("speaker") == "assistant" for m in ws.json))
    ws.client_sends(text=json.dumps({"type": "end"}))
    await asyncio.wait_for(task, 3)


async def make_platform_admin(env, a_id, factory):
    await add_user(factory, a_id, "Platform", ["*"], "boss@a.test")
    async with factory() as db:
        uid = (await db.execute(select(User.id).where(User.email == "boss@a.test"))).scalar_one()
    env[0].state.settings.platform_admin_user_ids = [str(uid)]
    return await login(env, "boss@a.test")


async def rows(factory):
    async with factory() as db:
        return list((await db.execute(select(UsageSession))).scalars())


async def test_call_records_measured_usage_without_content(env):
    a, a_id, b, b_id, factory = await two(env)
    try:
        await make_call(env, a)
        (r,) = await rows(factory)
        assert r.business_id == a_id and r.source == "test_call"
        assert r.stt_seconds == 3 and r.tts_characters > 10 and r.llm_requests == 1
        assert r.llm_usage == [{"model": "m", "input_tokens": 100, "output_tokens": 20}]
        assert r.turns == 1 and r.latency_avg_ms is not None and r.latency_max_ms >= r.latency_avg_ms and r.failed_requests == 0
        blob = json.dumps([r.llm_usage, r.pricing_snapshot, r.missing_rates])
        assert CUSTOMER_WORDS not in blob and "We open" not in blob  # counts only
        assert r.cost_micro_usd == 0 and r.cost_complete is False and set(r.missing_rates) >= {"elevenlabs_stt", "elevenlabs_tts", "openai:m:input"}
    finally:
        await a.aclose(), await b.aclose()


async def test_cost_is_an_estimate_from_price_records_and_price_changes_do_not_rewrite_history(env):
    a, a_id, b, b_id, factory = await two(env)
    try:
        boss = await make_platform_admin(env, a_id, factory)
        for item, rate in (("elevenlabs_stt_usd_per_hour", "3.60"), ("elevenlabs_tts_usd_per_1k_chars", "1.00"),
                           ("openai:m:input_usd_per_mtok", "2"), ("openai:m:output_usd_per_mtok", "10")):
            r = await boss.post(f"{API}/platform/prices", json={"item": item, "rate": rate, "effective_from": YESTERDAY, "source_note": "test sheet"})
            assert r.status_code == 201, r.text
        await make_call(env, a)
        (first,) = await rows(factory)
        chars = first.tts_characters
        # 3 s at $3.60/h = 0.003; chars at $1/1k; 100 in at $2/M = 0.0002; 20 out at $10/M = 0.0002
        expected = 3000 + chars * 1000 + 200 + 200
        assert first.cost_complete and first.missing_rates == [] and first.cost_micro_usd == expected
        s = (await a.get(f"{API}/usage/summary")).json()
        assert s["cost_basis"] == "estimate" and s["total"]["calls"] == 1 and s["total"]["cost_complete"] is True
        assert s["total"]["estimated_cost_usd"] == f"{expected / 1_000_000:.6f}"
        assert s["by_model"] == [{"model": "m", "calls": 1, "input_tokens": 100, "output_tokens": 20}]
        # a future price is ignored; a newer price applies only to later calls
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        assert (await boss.post(f"{API}/platform/prices", json={"item": "elevenlabs_tts_usd_per_1k_chars", "rate": "50", "effective_from": tomorrow})).status_code == 201
        await make_call(env, a)
        second = sorted(await rows(factory), key=lambda x: x.ended_at)[-1]
        assert second.cost_micro_usd == 3000 + second.tts_characters * 1000 + 400
        assert (await boss.post(f"{API}/platform/prices", json={"item": "elevenlabs_tts_usd_per_1k_chars", "rate": "2.00", "effective_from": date.today().isoformat()})).status_code == 201
        await make_call(env, a)
        third = sorted(await rows(factory), key=lambda x: x.ended_at)[-1]
        assert third.cost_micro_usd == 3000 + third.tts_characters * 2000 + 400
        old = [r for r in await rows(factory) if r.id == first.id][0]
        assert old.cost_micro_usd == expected  # history untouched
        await boss.aclose()
    finally:
        await a.aclose(), await b.aclose()


async def test_each_business_sees_only_its_own_usage_and_needs_permission(env):
    a, a_id, b, b_id, factory = await two(env)
    try:
        await make_call(env, a)
        sa, sb = (await a.get(f"{API}/usage/summary")).json(), (await b.get(f"{API}/usage/summary")).json()
        assert sa["total"]["calls"] == 1 and sb["total"]["calls"] == 0 and sb["by_day"] == [] and sb["by_model"] == []
        assert len((await a.get(f"{API}/usage/calls")).json()["items"]) == 1
        cb = (await b.get(f"{API}/usage/calls")).json()
        assert cb["items"] == [] and cb["total"] == 0
        await add_user(factory, a_id, "Staff", ["cases:write", "customers:write"], "s@a.test")
        s = await login(env, "s@a.test")
        assert (await s.get(f"{API}/usage/summary")).status_code == 403 and (await s.get(f"{API}/usage/calls")).status_code == 403
        async with __import__("tests.api.conftest", fromlist=["make_client"]).make_client(env[0]) as anon:
            assert (await anon.get(f"{API}/usage/summary")).status_code == 401
        assert (await a.get(f"{API}/usage/summary?start=2026-01-01&end=2025-01-01")).status_code == 422
        assert (await a.get(f"{API}/usage/summary?start=2020-01-01&end=2026-01-01")).status_code == 422
        await s.aclose()
    finally:
        await a.aclose(), await b.aclose()


async def test_platform_reporting_is_for_listed_platform_admins_only(env):
    a, a_id, b, b_id, factory = await two(env)
    try:
        await make_call(env, a)
        # even a business Administrator is not a platform admin unless listed
        for path in ("/platform/usage", "/platform/prices"):
            assert (await a.get(API + path)).status_code == 404 and (await b.get(API + path)).status_code == 404
        assert (await a.post(f"{API}/platform/prices", json={"item": "elevenlabs_stt_usd_per_hour", "rate": "1", "effective_from": YESTERDAY})).status_code == 404
        boss = await make_platform_admin(env, a_id, factory)
        rep = (await boss.get(f"{API}/platform/usage")).json()
        assert rep["cost_basis"] == "estimate" and [x["business_id"] for x in rep["businesses"]] == [str(a_id)]
        assert set(rep["businesses"][0]) >= {"business_name", "calls", "estimated_cost_usd", "cost_complete"}
        assert "items" not in rep and CUSTOMER_WORDS not in json.dumps(rep)  # totals only
        assert (await boss.get(f"{API}/platform/usage?month=2026-13")).status_code == 422
        bad = [{"item": "bogus", "rate": "1"}, {"item": "elevenlabs_stt_usd_per_hour", "rate": "-1"}, {"item": "elevenlabs_stt_usd_per_hour", "rate": "abc"},
               {"item": "openai:m:input_usd_per_mtok", "rate": "NaN"}, {"item": "openai::input_usd_per_mtok", "rate": "1"}]
        for body in bad:
            assert (await boss.post(f"{API}/platform/prices", json={**body, "effective_from": YESTERDAY})).status_code == 422, body
        async with factory() as db:
            acts = [e.action for e in (await db.execute(select(AuditEvent))).scalars()]
        assert "platform.usage_viewed" in acts
        await boss.aclose()
    finally:
        await a.aclose(), await b.aclose()


async def test_losing_a_usage_row_never_breaks_a_call_and_failures_are_counted(env, caplog):
    class Broken:
        def __call__(self):
            raise RuntimeError("database down")

    u = UsageRecord(business_id=uuid4(), session_id=uuid4(), stt_seconds=1, provider_errors=2, retries=3)
    caplog.set_level(logging.ERROR, logger="app.usage")
    now = datetime.now(timezone.utc)
    await record_call(Broken(), Settings(_env_file=None), u, source="test_call", started_at=now, ended_at=now)  # must not raise
    assert any("could not save usage" in r.getMessage() for r in caplog.records)
    a, a_id, b, _, factory = await two(env)
    try:
        await record_call(factory, Settings(_env_file=None), u.model_copy(update={"business_id": a_id}), source="test_call", started_at=now, ended_at=now)
        (r,) = await rows(factory)
        assert r.failed_requests == 2 and r.retries == 3
        s = (await a.get(f"{API}/usage/summary")).json()["total"]
        assert s["failed_requests"] == 2 and s["retries"] == 3
    finally:
        await a.aclose(), await b.aclose()


async def test_connection_retries_are_counted_in_the_calls_counter():
    from app.services.voice.errors import ProviderError
    from app.services.voice.providers.elevenlabs_common import connect_with_retries, retry_counter

    tries = []

    async def connector(url, headers):
        tries.append(1)
        if len(tries) < 3:
            raise OSError("flaky")
        return object()

    counter = [0]
    retry_counter.set(counter)
    await connect_with_retries(connector, "wss://x", "k", timeout_seconds=1, max_retries=3, backoff_seconds=0)
    assert counter[0] == 2
