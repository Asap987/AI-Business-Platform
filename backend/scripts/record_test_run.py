"""Run the real test suite and record the result for the project dashboard.

    cd backend
    python scripts/record_test_run.py                 # backend tests on the database named by TEST_DATABASE_URL (SQLite if unset)
    python scripts/record_test_run.py --frontend      # also run tsc, lint and build in ../frontend and record pass/fail

The dashboard only ever shows results recorded here, each with the time and the commit it ran against; it marks them stale when old or
when the checked-out commit has moved on. Failure entries hold test names only. DATABASE_URL must point at the app database.
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.config import Settings  # noqa: E402
from app.database.connection import make_engine, make_session_factory  # noqa: E402
from app.database.models import ProjectTestRun  # noqa: E402
from app.services.project_tracker import parse_junit  # noqa: E402


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    except Exception:
        return ""


def run_checks() -> dict[str, bool]:
    front = ROOT.parent / "frontend"
    out = {}
    for name, cmd in (("tsc", ["npx", "tsc", "--noEmit"]), ("lint", ["npm", "run", "lint"]), ("build", ["npm", "run", "build"])):
        out[name] = subprocess.run(cmd, cwd=front, capture_output=True).returncode == 0
        print(f"{name}: {'pass' if out[name] else 'FAIL'}")
    return out


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frontend", action="store_true")
    args = ap.parse_args()
    import os
    if os.environ.get("TEST_DATABASE_URL") and os.environ.get("TEST_DATABASE_URL") == os.environ.get("DATABASE_URL"):
        print("Refusing: TEST_DATABASE_URL equals DATABASE_URL. The tests empty their database, which would erase the dashboard data.")
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        xml = Path(tmp) / "r.xml"
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", f"--junitxml={xml}"], cwd=ROOT)
        if not xml.exists():
            print("pytest produced no results file; nothing recorded.")
            return 2
        result = parse_junit(xml.read_text(encoding="utf-8"))
    checks = run_checks() if args.frontend else {}
    factory = make_session_factory(make_engine(Settings()))
    async with factory() as db:
        db.add(ProjectTestRun(source="pytest", commit=git("rev-parse", "--short", "HEAD"), checks=checks, **result))
        await db.commit()
    print(f"Recorded: {result['passed']} passed, {result['failed']} failed, {result['skipped']} skipped of {result['total']} (pytest exit {proc.returncode}).")
    return 0 if proc.returncode == 0 and all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
