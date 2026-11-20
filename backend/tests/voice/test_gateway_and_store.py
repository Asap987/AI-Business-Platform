from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.services.voice.business_gateway import BusinessData, InMemoryBusinessGateway
from app.services.voice.schemas.voice_session import SessionState
from app.services.voice.session_store import InMemorySessionStore, SessionLimitError


def gw():
    g = InMemoryBusinessGateway()
    a, b = uuid4(), uuid4()
    g.register_business(a, BusinessData(knowledge=["Acme opens 8am to 5pm Monday to Friday."], departments=["Delivery"]))
    g.register_business(b, BusinessData(knowledge=["Beta Foods secret price list: rice 50."], departments=["Sales"]))
    return g, a, b


async def run(g, biz, tool, args, session=None):
    return await g.execute(business_id=biz, session_id=session or uuid4(), tool_name=tool, arguments=args)


async def test_knowledge_search_never_crosses_businesses():
    g, a, b = gw()
    mine = await run(g, a, "search_knowledge", {"query": "opening hours Monday"})
    assert mine.ok and "8am" in mine.summary
    other = await run(g, a, "search_knowledge", {"query": "secret price rice"})
    assert other.ok and other.data["results"] == [] and "Beta" not in other.summary


async def test_cases_are_stored_only_under_the_calling_business():
    g, a, b = gw()
    r = await run(g, a, "create_case", {"title": "Late parcel", "department": "Delivery"})
    assert r.ok and len(g.data_for(a).cases) == 1 and g.data_for(b).cases == []
    # a department that belongs to another business does not exist here
    bad = await run(g, a, "create_case", {"title": "Late parcel", "department": "Sales"})
    assert not bad.ok and len(g.data_for(a).cases) == 1


async def test_unknown_business_tool_and_disabled_tool_all_get_the_same_refusal():
    g, a, _ = gw()
    g.data_for(a).enabled_tools = {"search_knowledge"}
    unknown_biz = await run(g, uuid4(), "search_knowledge", {"query": "hours"})
    disabled = await run(g, a, "create_case", {"title": "Late parcel"})
    nonexistent = await run(g, a, "run_sql", {"q": "select 1"})
    assert {unknown_biz.summary, disabled.summary, nonexistent.summary} == {"That action is not available."}
    assert not any(r.ok for r in (unknown_biz, disabled, nonexistent))


async def test_invalid_arguments_do_nothing():
    g, a, _ = gw()
    r = await run(g, a, "create_case", {"title": ""})
    assert not r.ok and g.data_for(a).cases == []
    r = await run(g, a, "create_case", {"title": "ok title", "department": "x" * 500})
    assert not r.ok


async def test_only_enabled_tools_are_listed():
    g, a, b = gw()
    g.data_for(b).enabled_tools = {"search_knowledge"}
    assert {t.name for t in await g.list_tools(a, None)} == {"search_knowledge", "create_case", "escalate_to_human"}
    assert {t.name for t in await g.list_tools(b, None)} == {"search_knowledge"}
    assert await g.list_tools(uuid4(), None) == []


async def test_escalation_is_recorded_with_its_session():
    g, a, _ = gw()
    sid = uuid4()
    r = await run(g, a, "escalate_to_human", {"reason": "customer asked for a person"}, sid)
    assert r.ok and g.data_for(a).escalations == [(sid, "customer asked for a person")]


# ------------------------------------------------------------------- sessions
def store(**kw):
    return InMemorySessionStore(Settings(_env_file=None, **kw))


def test_a_session_is_invisible_to_other_businesses():
    st, a, b = store(), uuid4(), uuid4()
    s = st.create(a)
    assert st.get(a, s.session_id) is s
    assert st.get(b, s.session_id) is None
    assert st.get(a, uuid4()) is None


def test_concurrent_session_limit_is_per_business_and_frees_on_end():
    st, a, b = store(voice_max_concurrent_sessions_per_business=2), uuid4(), uuid4()
    s1, _ = st.create(a), st.create(a)
    with pytest.raises(SessionLimitError):
        st.create(a)
    st.create(b)  # another business is unaffected
    st.end(s1)
    st.create(a)


def test_new_session_rate_limit():
    st, a = store(voice_max_new_sessions_per_minute_per_business=2), uuid4()
    st.create(a), st.create(a)
    with pytest.raises(SessionLimitError):
        st.create(a)


def test_sweep_ends_silent_and_overlong_sessions_only():
    st, a = store(voice_silence_timeout_seconds=30, voice_session_max_seconds=900), uuid4()
    fresh, silent, long_ = st.create(a), st.create(a), st.create(a)
    now = datetime.now(timezone.utc)
    silent.last_activity_at = now - timedelta(seconds=31)
    long_.started_at = now - timedelta(seconds=901)
    ended = st.sweep(now)
    assert {s.session_id for s in ended} == {silent.session_id, long_.session_id}
    assert fresh.state is not SessionState.ENDED and silent.ended_at is not None


def test_ended_sessions_can_be_discarded_but_live_ones_cannot():
    st, a = store(), uuid4()
    s = st.create(a)
    st.discard(s)
    assert st.get(a, s.session_id) is s
    st.end(s)
    st.discard(s)
    assert st.get(a, s.session_id) is None
