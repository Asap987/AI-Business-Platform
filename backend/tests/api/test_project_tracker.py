from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace as NS

from sqlalchemy import select

from app.database.models import AuditEvent, ProjectTestRun
from app.services import project_tracker as pt
from tests.api.conftest import make_client
from tests.api.test_customers_cases import two
from tests.api.test_usage import make_platform_admin

API = "/api/v1/platform"
EVIDENCE = {"evidence_kind": "passing_test", "evidence": "tests/api/test_x.py passes on SQLite and PostgreSQL"}


def task(**kw):
    return {"module": "core", "title": "A task", "weight": 2, **kw}


async def add(c, **kw):
    r = await c.post(f"{API}/project/tasks", json=task(**kw))
    assert r.status_code == 201, r.text
    return r.json()


async def overview(c):
    r = await c.get(f"{API}/project")
    assert r.status_code == 200, r.text
    return r.json()


# ---- access ------------------------------------------------------------------------------------------------------

async def test_only_listed_platform_admins_can_reach_the_tracker(env):
    a, a_id, b, _, factory = await two(env)
    try:
        boss = await make_platform_admin(env, a_id, factory)
        await add(boss)
        probes = [("get", "/project", None), ("post", "/project/tasks", task()), ("post", "/project/milestones", {"name": "Alpha", "target_date": "2027-01-01"}),
                  ("post", "/project/external", {"name": "Key", "category": "awaiting_us"}), ("post", "/project/finance", {"label": "x y z", "category": "api", "kind": "estimate", "amount_usd": "1"})]
        for c in (a, b):  # a business Administrator, and another business: both get the 404 of a route that does not exist
            for method, path, body in probes:
                r = await getattr(c, method)(API + path, **({"json": body} if body else {}))
                assert r.status_code == 404, (method, path)
            assert (await c.get(f"{API}/access")).json() == {"platform_admin": False}
        assert (await boss.get(f"{API}/access")).json() == {"platform_admin": True}
        async with make_client(env[0]) as anon:
            assert (await anon.get(f"{API}/project")).status_code == 401
            assert (await anon.get(f"{API}/access")).status_code == 401
        await boss.aclose()
    finally:
        await a.aclose(); await b.aclose()


async def test_nothing_from_customer_businesses_appears_in_the_tracker(env):
    a, a_id, b, _, factory = await two(env)
    try:
        boss = await make_platform_admin(env, a_id, factory)
        body = (await boss.get(f"{API}/project")).text
        assert "Alpha" not in body and "Beta" not in body and "a@a.test" not in body and "b@b.test" not in body
        await boss.aclose()
    finally:
        await a.aclose(); await b.aclose()


# ---- progress is arithmetic, not opinion ----------------------------------------------------------------------------

async def test_completion_is_weight_of_completed_tasks_only(env):
    a, a_id, b, _, factory = await two(env)
    try:
        boss = await make_platform_admin(env, a_id, factory)
        await add(boss, title="Done one", weight=3, status="completed", **EVIDENCE)
        await add(boss, title="Half done", weight=3, status="in_progress")
        await add(boss, title="Not begun", weight=4)
        o = (await overview(boss))["overall"]
        assert o["weight_done"] == 3 and o["weight_total"] == 10 and o["percent"] == 30.0  # in-progress work counts for nothing
        assert o["counts"]["completed"] == 1 and o["counts"]["in_progress"] == 1 and o["counts"]["not_started"] == 1
        core = [m for m in (await overview(boss))["modules"] if m["key"] == "core"][0]
        assert core["percent"] == 30.0 and core["remaining"] == 2 and core["status"] == "In progress" and core["next_action"] == "Half done"
        empty = [m for m in (await overview(boss))["modules"] if m["key"] == "deployment"][0]
        assert empty["percent"] == 0.0 and empty["tasks"] == 0 and empty["status"] == "No tasks yet"
        await boss.aclose()
    finally:
        await a.aclose(); await b.aclose()


async def test_completed_needs_evidence_and_finished_dependencies(env):
    a, a_id, b, _, factory = await two(env)
    try:
        boss = await make_platform_admin(env, a_id, factory)
        r = await boss.post(f"{API}/project/tasks", json=task(status="completed"))
        assert r.status_code == 422 and "evidence" in r.json()["detail"].lower()
        r = await boss.post(f"{API}/project/tasks", json=task(status="completed", evidence_kind="passing_test", evidence="ok"))
        assert r.status_code == 422  # evidence too thin
        base = await add(boss, title="Base work")
        top = await add(boss, title="Depends on base", depends_on=[base["id"]])
        r = await boss.patch(f"{API}/project/tasks/{top['id']}", json={"status": "completed", **EVIDENCE})
        assert r.status_code == 422 and "Base work" in r.json()["detail"]
        assert (await boss.patch(f"{API}/project/tasks/{base['id']}", json={"status": "completed", **EVIDENCE})).status_code == 200
        r = await boss.patch(f"{API}/project/tasks/{top['id']}", json={"status": "completed", **EVIDENCE})
        assert r.status_code == 200 and r.json()["completed_at"]
        # re-opening clears completion
        r = await boss.patch(f"{API}/project/tasks/{top['id']}", json={"status": "testing"})
        assert r.status_code == 200 and r.json()["completed_at"] is None
        # blocked needs a reason
        assert (await boss.patch(f"{API}/project/tasks/{top['id']}", json={"status": "blocked"})).status_code == 422
        assert (await boss.patch(f"{API}/project/tasks/{top['id']}", json={"status": "blocked", "blocker": "Waiting for the key"})).status_code == 200
        await boss.aclose()
    finally:
        await a.aclose(); await b.aclose()


async def test_dependency_rules_loops_unknown_ids_and_deletion(env):
    a, a_id, b, _, factory = await two(env)
    try:
        boss = await make_platform_admin(env, a_id, factory)
        t1, t2 = await add(boss, title="First task"), await add(boss, title="Second task")
        assert (await boss.patch(f"{API}/project/tasks/{t2['id']}", json={"depends_on": [t1["id"]]})).status_code == 200
        r = await boss.patch(f"{API}/project/tasks/{t1['id']}", json={"depends_on": [t2["id"]]})
        assert r.status_code == 422 and "loop" in r.json()["detail"]
        assert (await boss.patch(f"{API}/project/tasks/{t1['id']}", json={"depends_on": [t1["id"]]})).status_code == 422
        assert (await boss.patch(f"{API}/project/tasks/{t1['id']}", json={"depends_on": ["00000000-0000-0000-0000-000000000000"]})).status_code == 422
        assert (await boss.delete(f"{API}/project/tasks/{t1['id']}")).status_code == 409  # t2 depends on it
        assert (await boss.delete(f"{API}/project/tasks/{t2['id']}")).status_code == 204
        assert (await boss.delete(f"{API}/project/tasks/{t1['id']}")).status_code == 204
        assert (await boss.patch(f"{API}/project/tasks/{t1['id']}", json={"title": "Gone"})).status_code == 404
        for bad in ({"module": "nonsense"}, {"status": "done"}, {"weight": 0}, {"weight": 11}, {"title": "ab"}, {"unknown": 1}, {"is_launch": True},
                    {"start_date": "2027-02-01", "deadline": "2027-01-01"}):
            assert (await boss.post(f"{API}/project/tasks", json=task(**bad))).status_code == 422, bad
        await boss.aclose()
    finally:
        await a.aclose(); await b.aclose()


async def test_changes_are_audited_without_content(env):
    a, a_id, b, _, factory = await two(env)
    try:
        boss = await make_platform_admin(env, a_id, factory)
        t = await add(boss, title="Secret-sounding title", notes="private notes")
        await boss.patch(f"{API}/project/tasks/{t['id']}", json={"status": "in_progress"})
        async with factory() as db:
            ev = [e for e in (await db.execute(select(AuditEvent))).scalars() if e.action.startswith("project.")]
        assert {e.action for e in ev} == {"project.task_added", "project.task_updated"}
        assert "Secret-sounding" not in str([e.detail for e in ev]) and "private notes" not in str([e.detail for e in ev])
        await boss.aclose()
    finally:
        await a.aclose(); await b.aclose()


# ---- milestones, external items, money, launch --------------------------------------------------------------------

async def test_milestones_external_finance_and_launch_checklist(env):
    a, a_id, b, _, factory = await two(env)
    try:
        boss = await make_platform_admin(env, a_id, factory)
        past = (date.today() - timedelta(days=3)).isoformat()
        m = (await boss.post(f"{API}/project/milestones", json={"name": "Live voice pilot", "phase": "Pilot", "target_date": past})).json()
        assert (await boss.post(f"{API}/project/milestones", json={"name": "Bad dates", "start_date": "2027-02-01", "target_date": "2027-01-01"})).status_code == 422
        o = await overview(boss)
        assert o["milestones"][0]["overdue"] is True and o["milestones"][0]["reached_at"] is None
        await boss.patch(f"{API}/project/milestones/{m['id']}", json={"name": "Live voice pilot", "target_date": past, "reached": True})
        assert (await overview(boss))["milestones"][0]["overdue"] is False
        e = (await boss.post(f"{API}/project/external", json={"name": "OpenAI key", "category": "awaiting_us", "owner": "Owner"})).json()
        await boss.patch(f"{API}/project/external/{e['id']}", json={"name": "OpenAI key", "category": "completed"})
        assert (await overview(boss))["external"][0]["category"] == "completed"
        assert (await boss.post(f"{API}/project/external", json={"name": "x y z", "category": "waiting"})).status_code == 422
        # money: estimates, actuals and outstanding commitments stay apart; nothing is invented
        for kind, amount, state in (("estimate", "20.50", ""), ("actual", "3.25", ""), ("commitment", "100", "outstanding"), ("commitment", "40", "settled")):
            assert (await boss.post(f"{API}/project/finance", json={"label": f"{kind} item", "category": "telephony", "kind": kind, "amount_usd": amount, "state": state})).status_code == 201
        fin = (await overview(boss))["finance"]
        assert fin["totals"] == {"estimate": "20.500000", "actual": "3.250000", "commitment": "100.000000"}
        assert fin["api_usage_this_month"]["basis"] == "estimate from recorded usage" and fin["api_usage_this_month"]["estimated_cost_usd"] == "0.000000"
        for bad in ({"amount_usd": "-1"}, {"amount_usd": "abc"}, {"amount_usd": "NaN"}, {"kind": "commitment", "state": ""}):
            body = {"label": "bad item", "category": "api", "kind": "estimate", "amount_usd": "1", **bad}
            assert (await boss.post(f"{API}/project/finance", json=body)).status_code == 422, bad
        # launch readiness is only 'ready' when every launch task in the area is completed
        await add(boss, title="Isolation test pass", is_launch=True, launch_area="data_isolation", status="completed", **EVIDENCE)
        await add(boss, title="Pen test", is_launch=True, launch_area="security")
        launch = {x["area"]: x for x in (await overview(boss))["launch"]}
        assert launch["data_isolation"]["ready"] is True and launch["security"]["ready"] is False and launch["backup"]["has_items"] is False and launch["backup"]["ready"] is False
        await boss.aclose()
    finally:
        await a.aclose(); await b.aclose()


# ---- test results are never passed off as current --------------------------------------------------------------------

async def test_latest_test_run_reports_its_age_and_staleness(env):
    a, a_id, b, _, factory = await two(env)
    try:
        boss = await make_platform_admin(env, a_id, factory)
        assert (await overview(boss))["tests"]["latest"] is None
        async with factory() as db:
            db.add(ProjectTestRun(ran_at=datetime.now(timezone.utc) - timedelta(hours=60), commit="abc1234", total=10, passed=9, failed=1, skipped=0, by_module={"core": {"passed": 9, "failed": 1, "skipped": 0}}, failures=["t::x"]))
            await db.commit()
        t = (await overview(boss))["tests"]
        assert t["latest"]["stale"] is True and t["latest"]["age_hours"] >= 60 and t["latest"]["failed"] == 1 and t["latest"]["failures"] == ["t::x"]
        assert t["coverage_note"] and t["latest"]["coverage_pct"] is None  # coverage is not invented
        core = [m for m in (await overview(boss))["modules"] if m["key"] == "core"][0]
        assert core["tests"] == {"passed": 9, "failed": 1, "skipped": 0}
        await boss.aclose()
    finally:
        await a.aclose(); await b.aclose()


# ---- pure rules ------------------------------------------------------------------------------------------------------

def test_run_state_flags_old_runs_and_other_commits():
    now = datetime(2026, 11, 22, 12, tzinfo=timezone.utc)
    fresh = pt.run_state(now - timedelta(hours=2), "abc1234", "abc1234", now)
    assert fresh == {"age_hours": 2.0, "stale": False, "matches_head": True}
    assert pt.run_state(now - timedelta(hours=2), "abc1234", "def5678", now)["stale"] is True  # code has moved on
    assert pt.run_state(now - timedelta(hours=30), "abc1234", None, now)["stale"] is True
    assert pt.run_state(now - timedelta(hours=1), "", None, now)["matches_head"] is None


def test_parse_junit_counts_and_names_only():
    xml = ('<testsuites><testsuite><testcase classname="tests.api.test_team" name="a" time="0.5"/>'
           '<testcase classname="tests.api.test_team" name="b" time="0.5"><failure message="SECRET output">trace</failure></testcase>'
           '<testcase classname="tests.voice.test_evaluation" name="c" time="1"><skipped/></testcase></testsuite></testsuites>')
    r = pt.parse_junit(xml)
    assert (r["total"], r["passed"], r["failed"], r["skipped"], r["duration_s"]) == (3, 1, 1, 1, 2.0)
    assert r["by_module"]["admin"] == {"passed": 1, "failed": 1, "skipped": 0} and r["by_module"]["voice"]["skipped"] == 1
    assert r["failures"] == ["tests.api.test_team::b"] and "SECRET" not in str(r)


def test_next_action_prefers_started_then_priority_and_skips_blocked_chains():
    base = dict(updated_at=datetime.now(timezone.utc), deadline=None, blocker="")
    a = NS(id="a", title="Low", status="not_started", priority="low", depends_on=[], **base)
    b = NS(id="b", title="Critical", status="not_started", priority="critical", depends_on=[], **base)
    c = NS(id="c", title="Waiting", status="not_started", priority="critical", depends_on=["a"], **base)
    assert pt.next_action([a, b, c]) == "Critical"
    b.status = "completed"
    assert pt.next_action([a, b, c]) == "Low"  # 'Waiting' is not ready until its dependency is done
    assert pt.next_action([NS(id="z", title="Done", status="completed", priority="low", depends_on=[], **base)]) is None
