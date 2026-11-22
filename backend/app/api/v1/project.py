"""Internal project tracker API. Reachable ONLY by users listed in PLATFORM_ADMIN_USER_IDS (everyone else gets 404, as
if the route did not exist). The data is platform-level, never customer data, and is never shown to customer
organisations. A task can be completed only with evidence and after its dependencies; progress is the weight of completed
tasks, nothing else. Changes are recorded in the audit log with ids only."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import Principal, current_principal, get_db
from app.api.v1.usage import platform_admin
from app.database.models import (ProjectExternal, ProjectFinance, ProjectMilestone, ProjectTask, ProjectTestRun, UsageSession)
from app.services import audit
from app.services import project_tracker as pt
from app.services.usage_store import aware, usd

router = APIRouter(prefix="/platform", tags=["project"])

Status = Literal["not_started", "in_progress", "awaiting_external", "awaiting_approval", "testing", "completed", "blocked"]
Priority = Literal["low", "medium", "high", "critical"]
EvidenceKind = Literal["merged_commit", "passing_test", "integration", "documented_verification"]
Area = Literal["security", "data_isolation", "voice_quality", "call_transfers", "email_delivery", "monitoring", "backup"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskIn(Strict):
    module: str
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=4000)
    status: Status = "not_started"
    priority: Priority = "medium"
    weight: int = Field(default=1, ge=1, le=10)
    start_date: date | None = None
    deadline: date | None = None
    blocker: str = Field(default="", max_length=1000)
    notes: str = Field(default="", max_length=4000)
    depends_on: list[UUID] = Field(default_factory=list)
    evidence_kind: EvidenceKind | None = None
    evidence: str = Field(default="", max_length=2000)
    is_launch: bool = False
    launch_area: Area | None = None


class TaskPatch(Strict):
    module: str | None = None
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    status: Status | None = None
    priority: Priority | None = None
    weight: int | None = Field(default=None, ge=1, le=10)
    start_date: date | None = None
    deadline: date | None = None
    blocker: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=4000)
    depends_on: list[UUID] | None = None
    evidence_kind: EvidenceKind | None = None
    evidence: str | None = Field(default=None, max_length=2000)
    is_launch: bool | None = None
    launch_area: Area | None = None


class MilestoneIn(Strict):
    name: str = Field(min_length=3, max_length=200)
    phase: str = Field(default="", max_length=80)
    description: str = Field(default="", max_length=1000)
    start_date: date | None = None
    target_date: date
    reached: bool = False


class ExternalIn(Strict):
    name: str = Field(min_length=3, max_length=200)
    category: Literal["awaiting_us", "awaiting_provider", "awaiting_approval", "completed"]
    owner: str = Field(default="", max_length=200)
    detail: str = Field(default="", max_length=2000)


class FinanceIn(Strict):
    label: str = Field(min_length=3, max_length=200)
    category: Literal["api", "telephony", "email", "hosting", "other"]
    kind: Literal["estimate", "actual", "commitment"]
    amount_usd: str = Field(max_length=20)
    period: str = Field(default="", max_length=40)
    state: Literal["", "outstanding", "settled"] = ""
    note: str = Field(default="", max_length=1000)


def _iso(d) -> str | None:
    return d.isoformat() if d else None


def _task(t: ProjectTask, by_id: dict[str, ProjectTask]) -> dict:
    deps = [{"id": d, "title": by_id[d].title, "status": by_id[d].status} for d in (t.depends_on or []) if d in by_id]
    return {"id": str(t.id), "module": t.module, "title": t.title, "description": t.description, "status": t.status, "priority": t.priority,
            "weight": t.weight, "start_date": _iso(t.start_date), "deadline": _iso(t.deadline), "blocker": t.blocker, "notes": t.notes,
            "depends_on": deps, "evidence_kind": t.evidence_kind, "evidence": t.evidence, "is_launch": t.is_launch, "launch_area": t.launch_area,
            "completed_at": _iso(t.completed_at), "updated_at": aware(t.updated_at).isoformat(),
            "overdue": bool(t.deadline and t.deadline < date.today() and t.status != "completed")}


async def _all_tasks(db: AsyncSession) -> list[ProjectTask]:
    return list((await db.execute(select(ProjectTask).order_by(ProjectTask.created_at, ProjectTask.title))).scalars())


def _money(text: str) -> int:
    try:
        v = Decimal(text)
    except InvalidOperation:
        raise HTTPException(422, "The amount must be a plain number.") from None
    if not v.is_finite() or v < 0 or v > 10_000_000:
        raise HTTPException(422, "The amount must be between 0 and 10,000,000.")
    return int((v * 1_000_000).to_integral_value())


async def _note(db: AsyncSession, p: Principal, action: str, **detail) -> None:
    audit.record(db, p.business_id, p.user.id, action, **detail)


@router.get("/access")
async def access(request: Request, p: Principal = Depends(current_principal)):
    """Any signed-in user may ask; only the answer differs. Used by the app to decide whether to show the tracker link."""
    return {"platform_admin": str(p.user.id) in request.app.state.settings.platform_admin_user_ids}


@router.get("/project")
async def project(p: Principal = Depends(platform_admin), db: AsyncSession = Depends(get_db)):
    tasks = await _all_tasks(db)
    by_id = {str(t.id): t for t in tasks}
    runs = list((await db.execute(select(ProjectTestRun).order_by(ProjectTestRun.ran_at.desc()).limit(30))).scalars())
    head, log = pt.git_head_and_log()
    latest = None
    if runs:
        r = runs[0]
        latest = {"id": str(r.id), "ran_at": aware(r.ran_at).isoformat(), "commit": r.commit, "source": r.source, "total": r.total, "passed": r.passed, "failed": r.failed,
                  "skipped": r.skipped, "duration_s": r.duration_s, "coverage_pct": r.coverage_pct, "checks": r.checks, "failures": r.failures,
                  **pt.run_state(r.ran_at, r.commit, head)}
    mods = pt.module_summaries(tasks)
    tested = {k for r in runs[:1] for k, v in (r.by_module or {}).items() if sum(v.values())}
    for m in mods:
        m["tests"] = (runs[0].by_module or {}).get(m["key"]) if runs else None
        m["thin_test_coverage"] = bool(runs) and m["key"] not in tested and m["tasks"] > 0
    milestones = list((await db.execute(select(ProjectMilestone).order_by(ProjectMilestone.target_date))).scalars())
    external = list((await db.execute(select(ProjectExternal).order_by(ProjectExternal.category, ProjectExternal.name))).scalars())
    finance = list((await db.execute(select(ProjectFinance).order_by(ProjectFinance.created_at.desc()))).scalars())
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    api_micro = (await db.execute(select(func.coalesce(func.sum(UsageSession.cost_micro_usd), 0)).where(UsageSession.ended_at >= month_start))).scalar_one()
    api_incomplete = (await db.execute(select(func.count()).select_from(UsageSession).where(UsageSession.ended_at >= month_start, UsageSession.cost_complete.is_(False)))).scalar_one()
    fin_rows = [{"id": str(f.id), "label": f.label, "category": f.category, "kind": f.kind, "amount_usd": usd(f.amount_micro_usd), "period": f.period, "state": f.state, "note": f.note} for f in finance]
    sums = {k: usd(sum(f.amount_micro_usd for f in finance if f.kind == k and (k != "commitment" or f.state == "outstanding"))) for k in pt.FINANCE_KINDS}
    return {
        "generated_at": now.isoformat(), "git_head": head,
        "overall": pt.completion(tasks), "modules": mods, "tasks": [_task(t, by_id) for t in tasks],
        "launch": pt.launch_readiness(tasks),
        "milestones": [{"id": str(m.id), "name": m.name, "phase": m.phase, "description": m.description, "start_date": _iso(m.start_date), "target_date": _iso(m.target_date),
                        "reached_at": _iso(m.reached_at), "overdue": bool(not m.reached_at and m.target_date < date.today())} for m in milestones],
        "external": [{"id": str(e.id), "name": e.name, "category": e.category, "owner": e.owner, "detail": e.detail, "updated_at": aware(e.updated_at).isoformat()} for e in external],
        "tests": {"latest": latest, "history": [{"ran_at": aware(r.ran_at).isoformat(), "commit": r.commit, "total": r.total, "passed": r.passed, "failed": r.failed, "skipped": r.skipped} for r in reversed(runs)],
                  "coverage_note": "Code coverage is not measured by the current test setup." if not (runs and runs[0].coverage_pct is not None) else None},
        "finance": {"rows": fin_rows, "totals": sums, "api_usage_this_month": {"estimated_cost_usd": usd(api_micro), "complete": api_incomplete == 0, "basis": "estimate from recorded usage"},
                    "note": "Estimates, recorded actual charges and commitments are kept apart. Nothing is an actual charge unless entered as one."},
        "recent_tasks": [{"id": str(t.id), "title": t.title, "status": t.status, "updated_at": aware(t.updated_at).isoformat()} for t in sorted(tasks, key=lambda x: aware(x.updated_at), reverse=True)[:8]],
        "git_log": log, "deployment": {"configured": False, "note": "No deployment is configured yet, so there is no deployment status."},
    }


async def _check_task(db: AsyncSession, task_id: UUID | None, data: dict, current: ProjectTask | None) -> None:
    if data["module"] not in pt.MODULES:
        raise HTTPException(422, "Unknown module.")
    tasks = await _all_tasks(db)
    known = {str(t.id): [str(x) for x in (t.depends_on or [])] for t in tasks}
    deps = [str(x) for x in data["depends_on"]]
    problem = pt.depends_ok(str(task_id) if task_id else None, deps, known)
    if problem:
        raise HTTPException(422, problem)
    by_id = {str(t.id): t for t in tasks}
    problem = pt.completion_problem(data["status"], data["evidence_kind"], data["evidence"], data["blocker"], [(by_id[d].title, by_id[d].status) for d in deps])
    if problem:
        raise HTTPException(422, problem)
    if data["is_launch"] and not data["launch_area"]:
        raise HTTPException(422, "A launch requirement needs an area.")
    if data["start_date"] and data["deadline"] and data["deadline"] < data["start_date"]:
        raise HTTPException(422, "The deadline cannot be before the start date.")


def _fields(body: BaseModel, current: ProjectTask | None) -> dict:
    base = {k: getattr(current, k) for k in TaskIn.model_fields} if current else {}
    base["depends_on"] = [UUID(x) for x in (current.depends_on or [])] if current else []
    new = body.model_dump(exclude_unset=True) if isinstance(body, TaskPatch) else body.model_dump()
    base.update(new)
    return base


def _write(t: ProjectTask, d: dict, user_id) -> None:
    for k in TaskIn.model_fields:
        setattr(t, k, [str(x) for x in d[k]] if k == "depends_on" else d[k])
    t.completed_at = (t.completed_at or datetime.now(timezone.utc)) if d["status"] == "completed" else None
    t.updated_by = user_id


@router.post("/project/tasks", status_code=201)
async def add_task(body: TaskIn, p: Principal = Depends(platform_admin), db: AsyncSession = Depends(get_db)):
    d = _fields(body, None)
    await _check_task(db, None, d, None)
    t = ProjectTask()
    _write(t, d, p.user.id)
    db.add(t)
    await db.flush()
    await _note(db, p, "project.task_added", task_id=t.id, status=t.status)
    await db.commit()
    return _task(t, {str(t.id): t})


@router.patch("/project/tasks/{task_id}")
async def edit_task(task_id: UUID, body: TaskPatch, p: Principal = Depends(platform_admin), db: AsyncSession = Depends(get_db)):
    t = await db.get(ProjectTask, task_id)
    if t is None:
        raise HTTPException(404, "Not found")
    d = _fields(body, t)
    await _check_task(db, task_id, d, t)
    before = t.status
    _write(t, d, p.user.id)
    await _note(db, p, "project.task_updated", task_id=t.id, status_from=before, status_to=t.status, fields=sorted(body.model_dump(exclude_unset=True)))
    await db.commit()
    return _task(t, {str(x.id): x for x in await _all_tasks(db)})


@router.delete("/project/tasks/{task_id}", status_code=204)
async def delete_task(task_id: UUID, p: Principal = Depends(platform_admin), db: AsyncSession = Depends(get_db)):
    t = await db.get(ProjectTask, task_id)
    if t is None:
        raise HTTPException(404, "Not found")
    users = [x.title for x in await _all_tasks(db) if str(task_id) in (x.depends_on or [])]
    if users:
        raise HTTPException(409, "Other tasks depend on this one: " + ", ".join(users[:3]) + ".")
    await db.delete(t)
    await _note(db, p, "project.task_deleted", task_id=task_id)
    await db.commit()


@router.post("/project/milestones", status_code=201)
async def add_milestone(body: MilestoneIn, p: Principal = Depends(platform_admin), db: AsyncSession = Depends(get_db)):
    if body.start_date and body.target_date < body.start_date:
        raise HTTPException(422, "The target date cannot be before the start date.")
    m = ProjectMilestone(name=body.name, phase=body.phase, description=body.description, start_date=body.start_date, target_date=body.target_date,
                         reached_at=datetime.now(timezone.utc) if body.reached else None)
    db.add(m)
    await db.flush()
    await _note(db, p, "project.milestone_added", milestone_id=m.id)
    await db.commit()
    return {"id": str(m.id)}


@router.patch("/project/milestones/{mid}")
async def edit_milestone(mid: UUID, body: MilestoneIn, p: Principal = Depends(platform_admin), db: AsyncSession = Depends(get_db)):
    m = await db.get(ProjectMilestone, mid)
    if m is None:
        raise HTTPException(404, "Not found")
    if body.start_date and body.target_date < body.start_date:
        raise HTTPException(422, "The target date cannot be before the start date.")
    m.name, m.phase, m.description, m.start_date, m.target_date = body.name, body.phase, body.description, body.start_date, body.target_date
    m.reached_at = (m.reached_at or datetime.now(timezone.utc)) if body.reached else None
    await _note(db, p, "project.milestone_updated", milestone_id=m.id, reached=bool(m.reached_at))
    await db.commit()
    return {"id": str(m.id)}


@router.delete("/project/milestones/{mid}", status_code=204)
async def delete_milestone(mid: UUID, p: Principal = Depends(platform_admin), db: AsyncSession = Depends(get_db)):
    m = await db.get(ProjectMilestone, mid)
    if m is None:
        raise HTTPException(404, "Not found")
    await db.delete(m)
    await _note(db, p, "project.milestone_deleted", milestone_id=mid)
    await db.commit()


@router.post("/project/external", status_code=201)
async def add_external(body: ExternalIn, p: Principal = Depends(platform_admin), db: AsyncSession = Depends(get_db)):
    e = ProjectExternal(**body.model_dump())
    db.add(e)
    await db.flush()
    await _note(db, p, "project.external_added", external_id=e.id)
    await db.commit()
    return {"id": str(e.id)}


@router.patch("/project/external/{eid}")
async def edit_external(eid: UUID, body: ExternalIn, p: Principal = Depends(platform_admin), db: AsyncSession = Depends(get_db)):
    e = await db.get(ProjectExternal, eid)
    if e is None:
        raise HTTPException(404, "Not found")
    for k, v in body.model_dump().items():
        setattr(e, k, v)
    await _note(db, p, "project.external_updated", external_id=e.id, category=e.category)
    await db.commit()
    return {"id": str(e.id)}


@router.delete("/project/external/{eid}", status_code=204)
async def delete_external(eid: UUID, p: Principal = Depends(platform_admin), db: AsyncSession = Depends(get_db)):
    e = await db.get(ProjectExternal, eid)
    if e is None:
        raise HTTPException(404, "Not found")
    await db.delete(e)
    await _note(db, p, "project.external_deleted", external_id=eid)
    await db.commit()


@router.post("/project/finance", status_code=201)
async def add_finance(body: FinanceIn, p: Principal = Depends(platform_admin), db: AsyncSession = Depends(get_db)):
    if body.kind == "commitment" and not body.state:
        raise HTTPException(422, "A commitment must be marked outstanding or settled.")
    f = ProjectFinance(label=body.label, category=body.category, kind=body.kind, amount_micro_usd=_money(body.amount_usd), period=body.period,
                       state=body.state if body.kind == "commitment" else "", note=body.note)
    db.add(f)
    await db.flush()
    await _note(db, p, "project.finance_added", finance_id=f.id, kind=f.kind, category=f.category)
    await db.commit()
    return {"id": str(f.id)}


@router.delete("/project/finance/{fid}", status_code=204)
async def delete_finance(fid: UUID, p: Principal = Depends(platform_admin), db: AsyncSession = Depends(get_db)):
    f = await db.get(ProjectFinance, fid)
    if f is None:
        raise HTTPException(404, "Not found")
    await db.delete(f)
    await _note(db, p, "project.finance_deleted", finance_id=fid)
    await db.commit()
