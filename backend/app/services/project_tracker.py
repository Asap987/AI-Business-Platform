"""Rules and calculations for the internal project tracker (pure functions, no database, so they are easy to test).

Progress is never guessed: a task counts only when it is ``completed`` and carries evidence; every percentage is the
weight of completed tasks divided by the weight of all tasks. Test results are only ever those recorded from a real run.
"""

from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

MODULES: dict[str, str] = {
    "core": "Core platform and backend", "tenancy": "Multi-organisation architecture", "admin": "Organisation administration dashboard",
    "ai": "AI conversation and intelligence engine", "knowledge": "Knowledge management and document processing",
    "integrations": "Database and external integrations", "voice": "Voice and speech-to-text", "telephony": "Telephony and call management",
    "routing": "Departmental call routing", "email": "Email and notifications", "security": "Security, privacy and compliance",
    "usage": "Usage monitoring and billing", "testing": "Testing and quality assurance", "deployment": "Deployment and production readiness",
}
STATUSES = ("not_started", "in_progress", "awaiting_external", "awaiting_approval", "testing", "completed", "blocked")
PRIORITIES = ("low", "medium", "high", "critical")
EVIDENCE_KINDS = ("merged_commit", "passing_test", "integration", "documented_verification")
EXTERNAL_CATEGORIES = ("awaiting_us", "awaiting_provider", "awaiting_approval", "completed")
FINANCE_KINDS = ("estimate", "actual", "commitment")
FINANCE_CATEGORIES = ("api", "telephony", "email", "hosting", "other")
LAUNCH_AREAS = ("security", "data_isolation", "voice_quality", "call_transfers", "email_delivery", "monitoring", "backup")
STALE_AFTER_HOURS = 24
_PRIORITY_RANK = {p: i for i, p in enumerate(reversed(PRIORITIES))}  # critical first

# test file stem -> module, for the per-module test breakdown
TEST_MODULES = {
    "test_auth": "core", "test_dashboard_tenancy": "tenancy", "test_customers_cases": "tenancy", "test_organization": "admin",
    "test_team": "admin", "test_settings": "admin", "test_knowledge": "knowledge", "test_voice_call": "voice",
    "test_voice_database_gateway": "ai", "test_elevenlabs_stt": "voice", "test_elevenlabs_tts": "voice", "test_evaluation": "voice",
    "test_openai_reasoning": "ai", "test_conversation_manager": "ai", "test_language_manager": "ai", "test_gateway_and_store": "ai",
    "test_config": "core", "test_usage": "usage", "test_privacy": "security", "test_privacy_audit": "security", "test_email": "email",
    "test_transfer": "routing", "test_project_tracker": "testing",
}


def module_for_test(classname_or_path: str) -> str:
    stem = classname_or_path.replace("\\", "/").split("/")[-1].removesuffix(".py").split(".")[-1]
    return TEST_MODULES.get(stem, "other")


# ---- tasks ----------------------------------------------------------------------------------------------------

def depends_ok(task_id: str | None, depends_on: list[str], known: dict[str, list[str]]) -> str | None:
    """Return a problem description, or None. ``known`` maps every existing task id to its own dependencies."""
    if len(depends_on) > 20 or len(set(depends_on)) != len(depends_on):
        return "Dependencies must be at most 20 distinct tasks."
    for d in depends_on:
        if d not in known:
            return "A dependency does not exist."
        if task_id is not None and d == task_id:
            return "A task cannot depend on itself."
    if task_id is not None:  # would this edge set create a loop?
        graph = {**known, task_id: depends_on}
        seen, stack = set(), list(depends_on)
        while stack:
            n = stack.pop()
            if n == task_id:
                return "Those dependencies would form a loop."
            if n in seen:
                continue
            seen.add(n)
            stack.extend(graph.get(n, []))
    return None


def completion_problem(status: str, evidence_kind: str | None, evidence: str, blocker: str, dep_statuses: list[tuple[str, str]]) -> str | None:
    """Rules for a status. ``dep_statuses`` is [(title, status)] of this task's dependencies."""
    if status == "completed":
        if evidence_kind not in EVIDENCE_KINDS or len(evidence.strip()) < 10:
            return "A completed task needs evidence: choose what kind (merged commit, passing test, integration, documented verification) and describe it."
        pending = [t for t, s in dep_statuses if s != "completed"]
        if pending:
            return "Finish its dependencies first: " + ", ".join(pending[:3]) + "."
    if status == "blocked" and not blocker.strip():
        return "Say what is blocking it."
    return None


def pct(done: int, total: int) -> float:
    return round(100 * done / total, 1) if total else 0.0


def completion(tasks: list[Any]) -> dict:
    total = sum(t.weight for t in tasks)
    done = sum(t.weight for t in tasks if t.status == "completed")
    counts = {s: sum(1 for t in tasks if t.status == s) for s in STATUSES}
    return {"percent": pct(done, total), "weight_done": done, "weight_total": total, "tasks": len(tasks), "counts": counts}


def next_action(tasks: list[Any]) -> str | None:
    by_id = {str(t.id): t for t in tasks}
    ready = [t for t in tasks if t.status in ("not_started", "in_progress", "testing") and all(by_id.get(d) is None or by_id[d].status == "completed" for d in (t.depends_on or []))]
    if not ready:
        return None
    ready.sort(key=lambda t: (t.status != "in_progress", _PRIORITY_RANK.get(t.priority, 9), t.deadline or date.max, t.title))
    return ready[0].title


def module_status(tasks: list[Any]) -> str:
    if not tasks:
        return "No tasks yet"
    s = {t.status for t in tasks}
    if s == {"completed"}:
        return "Complete"
    if "blocked" in s:
        return "Blocked"
    if s & {"in_progress", "testing"}:
        return "In progress"
    if s & {"awaiting_external", "awaiting_approval"} and not (s & {"not_started"}):
        return "Waiting on others"
    return "In progress" if "completed" in s else "Not started"


def module_summaries(tasks: list[Any]) -> list[dict]:
    by_id = {str(t.id): t for t in tasks}
    out = []
    for key, name in MODULES.items():
        ts = [t for t in tasks if t.module == key]
        c = completion(ts)
        deps = sorted({MODULES.get(by_id[d].module, by_id[d].module) for t in ts for d in (t.depends_on or []) if d in by_id and by_id[d].module != key})
        issues = [f"{t.title}: {t.blocker}" for t in ts if t.blocker.strip() and t.status != "completed"]
        latest = max((t.updated_at for t in ts), default=None)
        out.append({"key": key, "name": name, **c, "remaining": len(ts) - c["counts"]["completed"], "status": module_status(ts), "depends_on_modules": deps,
                    "known_issues": issues, "next_action": next_action(ts), "last_updated": latest.isoformat() if latest else None})
    return out


def launch_readiness(tasks: list[Any]) -> list[dict]:
    out = []
    for area in LAUNCH_AREAS:
        ts = [t for t in tasks if t.is_launch and t.launch_area == area]
        out.append({"area": area, "total": len(ts), "done": sum(1 for t in ts if t.status == "completed"),
                    "ready": bool(ts) and all(t.status == "completed" for t in ts), "has_items": bool(ts)})
    return out


# ---- test runs --------------------------------------------------------------------------------------------------

def parse_junit(xml_text: str) -> dict:
    """Counts from a pytest ``--junitxml`` file. Failure entries hold test names only, never output."""
    root = ET.fromstring(xml_text)
    total = passed = failed = skipped = 0
    by_module: dict[str, dict[str, int]] = defaultdict(lambda: {"passed": 0, "failed": 0, "skipped": 0})
    failures: list[str] = []
    duration = 0.0
    for case in root.iter("testcase"):
        module = module_for_test(case.get("classname", "").replace(".", "/") or case.get("file", ""))
        duration += float(case.get("time", 0) or 0)
        total += 1
        if case.find("failure") is not None or case.find("error") is not None:
            failed += 1
            by_module[module]["failed"] += 1
            failures.append(f"{case.get('classname', '')}::{case.get('name', '')}"[:200])
        elif case.find("skipped") is not None:
            skipped += 1
            by_module[module]["skipped"] += 1
        else:
            passed += 1
            by_module[module]["passed"] += 1
    return {"total": total, "passed": passed, "failed": failed, "skipped": skipped, "duration_s": round(duration, 2), "by_module": dict(by_module), "failures": failures[:50]}


def run_state(ran_at: datetime, commit: str, head: str | None, now: datetime | None = None) -> dict:
    """Never let an old run look current: say how old it is and whether it was for the code that is checked out now."""
    now = now or datetime.now(timezone.utc)
    ran = ran_at if ran_at.tzinfo else ran_at.replace(tzinfo=timezone.utc)
    age_h = (now - ran).total_seconds() / 3600
    matches = None if not head or not commit else head.startswith(commit) or commit.startswith(head)
    return {"age_hours": round(age_h, 1), "stale": age_h > STALE_AFTER_HOURS or matches is False, "matches_head": matches}


# ---- git ----------------------------------------------------------------------------------------------------------

def git_head_and_log(limit: int = 12) -> tuple[str | None, list[dict]]:
    """Latest commits from the repository this code runs in. Fixed arguments only; (None, []) if there is no repository."""
    root = Path(__file__).resolve().parents[3]
    if not (root / ".git").exists():
        return None, []
    try:
        run = lambda *a: subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True, timeout=5, check=True).stdout  # noqa: E731
        head = run("rev-parse", "--short", "HEAD").strip()
        lines = run("log", f"-n{int(limit)}", "--pretty=format:%h%x1f%aI%x1f%s").splitlines()
    except Exception:
        return None, []
    log = []
    for ln in lines:
        h, when, subject = (ln.split("\x1f") + ["", ""])[:3]
        log.append({"commit": h, "date": when, "subject": subject[:200]})
    return head, log
