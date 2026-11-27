"""Load the tracked tasks, milestones, external items and money notes into the project dashboard (platform tables).

    cd backend && python scripts/seed_project.py

Safe to run again: a task, milestone or item that already exists is left exactly as it is (your edits are never overwritten); only new ones are added.
Every status below states what was actually verified on 2026-11-22. A task is ``completed`` only with evidence that can be re-checked
(a named passing test file or a written verification). Work that exists only as an interface or a simulation is NOT completed.
Milestone dates are PROPOSED targets for the owner to edit, not promises.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.database.connection import make_engine, make_session_factory  # noqa: E402
from app.database.models import ProjectExternal, ProjectFinance, ProjectMilestone, ProjectTask  # noqa: E402

T, D, I = "passing_test", "documented_verification", "integration"
# (key, module, title, status, priority, weight, evidence_kind, evidence, blocker, depends_on keys, launch_area, description)
TASKS = [
    # ---- core
    ("core.api", "core", "FastAPI backend, configuration and health endpoint", "completed", "high", 3, T, "tests/api/test_auth.py and tests/test_config.py pass", "", [], None, ""),
    ("core.migrations", "core", "SQL migrations 0001 to 0010 applied to PostgreSQL 16", "completed", "high", 3, D, "Applied in order to a local PostgreSQL 16; the API suite passes on it", "", [], None, ""),
    ("core.pg-tests", "core", "API tests run on real PostgreSQL as well as SQLite", "completed", "high", 2, T, "TEST_DATABASE_URL run: 116 API tests pass on PostgreSQL 16", "", ["core.migrations"], None, ""),
    ("core.frontend", "core", "Next.js shell, sign-in, registration, navigation, branding", "completed", "high", 3, D, "tsc, lint and production build clean; Chromium end-to-end runs passed (team, knowledge, privacy, voice, nav, customers)", "", [], None, ""),
    ("core.merge", "core", "Merge the feature branch into main (or open a pull request)", "awaiting_approval", "medium", 1, None, "", "", [], None, "The owner has not chosen between a pull request and a direct merge."),
    # ---- tenancy
    ("tenancy.isolation", "tenancy", "Business taken from the session on every query; other businesses' ids give 404", "completed", "critical", 5, T, "Two-business tests across customers, cases, departments, employees, team, knowledge, privacy, usage, settings; mutation checks failed as expected", "", [], "data_isolation", ""),
    ("tenancy.roles", "tenancy", "Roles and permissions (Administrator, Manager, Employee) enforced by the API", "completed", "high", 3, T, "tests/api/test_team.py and permission 403 tests in each API test file", "", [], None, ""),
    ("tenancy.rls", "tenancy", "PostgreSQL row-level security as a second lock", "not_started", "medium", 3, None, "", "", ["tenancy.isolation"], "data_isolation", ""),
    ("tenancy.dept-perms", "tenancy", "Department-level data permissions", "not_started", "medium", 3, None, "", "", ["tenancy.roles"], None, ""),
    ("tenancy.pentest", "tenancy", "Independent isolation and penetration test", "not_started", "high", 4, None, "", "", ["tenancy.isolation"], "data_isolation", ""),
    # ---- admin
    ("admin.crm", "admin", "Customers and cases: create, edit, search, assign, history", "completed", "high", 3, T, "tests/api/test_customers_cases.py", "", [], None, ""),
    ("admin.customer-page", "admin", "Customer detail page with their cases", "completed", "medium", 2, D, "Chromium run 10 of 10 passed including other-business 404 and 390 px width", "", ["admin.crm"], None, ""),
    ("admin.org", "admin", "Departments and employees", "completed", "high", 3, T, "tests/api/test_organization.py", "", [], None, ""),
    ("admin.team", "admin", "Staff invitations, roles, disabling accounts", "completed", "high", 3, T, "tests/api/test_team.py and a Chromium run", "", [], None, ""),
    ("admin.settings-api", "admin", "PATCH /profile and PATCH /business endpoints", "completed", "medium", 2, T, "tests/api/test_settings.py with mutation checks", "", [], None, ""),
    ("admin.settings-screens", "admin", "Profile and Business settings screens", "completed", "high", 2, T, "tests/api/test_business_profile.py (5 tests, mutation-checked); Chromium run 12 of 12 checks incl. other-business view and 390 px", "", ["admin.settings-api"], None, "Branches, hours, policies, languages and service preferences are saved but not yet read by the assistants."),
    ("admin.org-profile", "admin", "Organisation profile: hours, contacts, languages, products, policies", "not_started", "high", 4, None, "", "", [], None, ""),
    ("admin.ai-config", "admin", "AI configuration screen: name, tone, language, voice, instructions", "not_started", "high", 4, None, "", "", ["admin.org-profile"], None, ""),
    ("admin.test-chat", "admin", "Text test chat and scripted scenarios before activation", "not_started", "medium", 3, None, "", "", ["admin.ai-config"], None, ""),
    ("admin.overview-kpis", "admin", "Dashboard KPIs: AI resolution rate and response time", "not_started", "low", 2, None, "", "", [], None, ""),
    ("admin.privacy", "admin", "Privacy controls and audit log screen", "completed", "high", 2, T, "tests/api/test_privacy_audit.py and a Chromium run", "", [], None, ""),
    ("admin.usage", "admin", "Usage and costs screen", "completed", "medium", 2, T, "tests/api/test_usage.py and a Chromium run (7 of 7)", "", ["usage.record"], None, ""),
    # ---- ai
    ("ai.reasoning", "ai", "OpenAI reasoning adapter, streaming and tool calls (offline)", "completed", "high", 3, T, "tests/voice/test_openai_reasoning.py with fakes", "", [], None, "Offline only. Live behaviour is a separate task."),
    ("ai.live-openai", "ai", "Verify the OpenAI adapter against the real API", "awaiting_external", "critical", 3, None, "", "Needs the OpenAI key as a server setting", ["ai.reasoning"], "voice_quality", ""),
    ("ai.manager", "ai", "Conversation manager: turns, interruption, language, hand-over", "completed", "high", 4, T, "tests/voice/test_conversation_manager.py", "", [], None, ""),
    ("ai.tools", "ai", "Validated backend tools only (no SQL); business scoped", "completed", "critical", 4, T, "tests/voice/test_voice_database_gateway.py and cross-business tool tests", "", [], None, ""),
    ("ai.route-intent", "ai", "Connect intent recognition to department transfer", "in_progress", "high", 3, None, "", "Tools are wired and tested with fakes; how the live model chooses them is unverified until credentials and privacy approval", ["routing.service"], None, ""),
    ("ai.injection", "ai", "Prompt-injection tests with hostile callers and documents", "not_started", "high", 3, None, "", "", [], "security", ""),
    ("ai.delta-horta", "ai", "Delta Horta scripted scenarios (transport versus storage, unverified capacity)", "not_started", "high", 3, None, "", "", ["admin.test-chat"], None, ""),
    # ---- knowledge
    ("kb.text", "knowledge", "Text documents, chunking, keyword search, published only", "completed", "high", 3, T, "tests/api/test_knowledge.py", "", [], None, ""),
    ("kb.upload", "knowledge", "Upload PDF, DOCX, CSV, XLSX and TXT with text extraction", "not_started", "high", 5, None, "", "", ["kb.text"], None, ""),
    ("kb.status", "knowledge", "Versions, processing status, reprocess, failed uploads", "not_started", "medium", 3, None, "", "", ["kb.upload"], None, ""),
    ("kb.semantic", "knowledge", "Semantic search with embeddings", "awaiting_approval", "low", 3, None, "", "No embeddings provider is approved", ["kb.text"], None, ""),
    ("kb.conflicts", "knowledge", "Detect missing or conflicting information", "not_started", "low", 2, None, "", "", ["kb.upload"], None, ""),
    # ---- integrations
    ("int.connections", "integrations", "Guided database and API connections with encrypted credentials", "not_started", "high", 5, None, "", "", [], None, ""),
    ("int.readonly", "integrations", "Read-only by default, validated write workflows", "not_started", "high", 3, None, "", "", ["int.connections"], None, ""),
    ("int.sync", "integrations", "Scheduled sync, webhooks, live retrieval, health display", "not_started", "medium", 4, None, "", "", ["int.connections"], None, ""),
    # ---- voice
    ("voice.adapters", "voice", "ElevenLabs speech and recognition adapters (offline)", "completed", "high", 3, T, "tests/voice/test_elevenlabs_stt.py and test_elevenlabs_tts.py with fakes", "", [], None, "Offline only."),
    ("voice.call", "voice", "Call runner and secure browser test-call WebSocket", "completed", "high", 3, T, "tests/api/test_voice_call.py (origin, session, permission, limits)", "", [], None, "Offline only."),
    ("voice.browser", "voice", "Browser microphone test page", "completed", "medium", 2, D, "Chromium run with a fake microphone and fake providers (barge-in verified)", "", ["voice.call"], None, "Not tried with a real microphone and real providers."),
    ("voice.probe", "voice", "Provider connection check before live calls", "completed", "high", 2, T, "Provider-check tests with fakes (offline)", "", [], None, ""),
    ("voice.live-check", "voice", "Run the live provider check with real keys", "awaiting_external", "critical", 3, None, "", "Needs OpenAI and ElevenLabs keys as server settings", ["voice.probe", "ai.live-openai"], "voice_quality", ""),
    ("voice.latency", "voice", "Measure real conversation latency and voice quality", "awaiting_external", "high", 3, None, "", "Needs live keys", ["voice.live-check"], "voice_quality", ""),
    ("voice.stt-framework", "voice", "Speech recognition evaluation framework", "completed", "high", 2, T, "tests/voice/test_evaluation.py (WER, term recall, latency)", "", [], None, ""),
    ("voice.stt-real", "voice", "Evaluate Ghanaian-English recognition on consented recordings", "awaiting_external", "critical", 4, None, "", "No recordings and no consent forms yet; ElevenLabs terms not yet confirmed", ["voice.stt-framework"], "voice_quality", ""),
    ("voice.keyterms", "voice", "Send business keywords to the recogniser", "not_started", "low", 1, None, "", "Request format must be confirmed against the live API first", ["voice.live-check"], None, ""),
    # ---- telephony
    ("tel.interface", "telephony", "Provider-independent telephony interface and simulated provider", "completed", "high", 2, T, "tests/api/test_transfer.py", "", [], None, "Simulation only: no real calls."),
    ("tel.compare", "telephony", "Provider comparison (Telnyx, Twilio, Africa's Talking) from public pages", "completed", "high", 2, D, "documentation/telephony-comparison.md with sources", "", [], None, ""),
    ("tel.confirmations", "telephony", "Written confirmations from the three providers", "awaiting_external", "high", 3, None, "", "Numbers, rates, streaming, SIP, transfers, concurrency, requirements not yet confirmed in writing", ["tel.compare"], None, ""),
    ("tel.select", "telephony", "Select the telephony provider", "awaiting_approval", "high", 2, None, "", "Owner approval needed; no spend before then", ["tel.confirmations"], None, ""),
    ("tel.adapter", "telephony", "Real provider adapter (Telnyx first, Twilio backup)", "not_started", "high", 5, None, "", "", ["tel.interface", "tel.select"], "call_transfers", ""),
    ("tel.numbers", "telephony", "Obtain a Ghana number (account documents, purchase)", "awaiting_approval", "high", 2, None, "", "Needs approval and business registration documents", ["tel.select"], None, ""),
    ("tel.audio", "telephony", "Phone audio path: 8 kHz resampling, streaming to the call runner", "not_started", "high", 3, None, "", "", ["tel.adapter"], "voice_quality", ""),
    ("tel.real-transfer", "telephony", "Real call transfer to a person, confirmed by the provider", "not_started", "critical", 4, None, "", "", ["tel.adapter", "routing.service"], "call_transfers", ""),
    # ---- routing
    ("routing.service", "routing", "Transfer decision logic with simulated provider", "completed", "high", 3, T, "tests/api/test_transfer.py (business scoping, attempts, honest outcomes, audit without numbers)", "", [], None, "Simulated; real transfers are a separate task."),
    ("routing.hours", "routing", "Department operating hours and availability", "completed", "high", 3, T, "tests/api/test_routing.py: hours rules, time zones, closed departments, availability endpoint; screen checked in Chromium", "", ["routing.service"], None, "Simulated provider only."),
    ("routing.extensions", "routing", "Employee extensions and availability", "completed", "medium", 2, T, "tests/api/test_routing.py: extension passed to provider, unavailable staff skipped, API validation and isolation", "", ["routing.service"], None, ""),
    ("routing.fallback", "routing", "Routing priorities and fallback rules", "completed", "medium", 3, T, "tests/api/test_routing.py: priority order, same-business fallback, loop cut, shared attempt budget, mutation-checked", "", ["routing.hours"], None, ""),
    ("routing.callback", "routing", "Callback requests and human escalation records", "completed", "high", 3, T, "tests/api/test_routing.py: callbacks API isolation, permissions, status rules, audit without numbers; Chromium run 12 of 13 checks plus a re-check", "", ["routing.service"], None, "A callback is a request, not a booked time."),
    ("routing.context", "routing", "Preserve conversation context across departments", "completed", "high", 3, T, "tests/api/test_handover.py and tests/voice/test_handover_manager.py: briefing carried to callbacks, people and department assistants; limits and business isolation mutation-checked", "", ["routing.service", "ai.manager"], None, "Tested with fakes only; how the live model behaves after a hand-over is unverified."),
    # ---- email
    ("email.service", "email", "Email service with Resend adapter, templates, invitations, reset, verification, notices (offline)", "completed", "high", 4, T, "tests/api/test_email.py and a Chromium run with a fake provider", "", [], None, "No email has been sent for real."),
    ("email.domain", "email", "Verify the sending domain in Resend and set the key", "awaiting_external", "high", 2, None, "", "Owner provides the domain and verifies DNS records", ["email.service"], "email_delivery", ""),
    ("email.live", "email", "Live delivery, expiry, token reuse and error tests after verification", "awaiting_external", "high", 3, None, "", "Needs a verified domain", ["email.domain"], "email_delivery", ""),
    ("email.enforce", "email", "Require a verified email once email is live", "not_started", "medium", 1, None, "", "", ["email.live"], None, ""),
    ("email.bounces", "email", "Bounce and complaint handling", "not_started", "low", 2, None, "", "", ["email.live"], None, ""),
    ("email.inapp", "email", "In-app notifications", "not_started", "low", 2, None, "", "", [], None, ""),
    # ---- security
    ("sec.auth", "security", "Argon2 passwords, server sessions, rate limits, single-use reset tokens", "completed", "critical", 4, T, "tests/api/test_auth.py and tests/api/test_email.py", "", [], None, ""),
    ("sec.audit", "security", "Append-only audit log for sensitive changes", "completed", "high", 2, T, "tests/api/test_privacy_audit.py (database trigger on PostgreSQL)", "", [], None, ""),
    ("sec.review", "security", "Privacy risk register and provider terms review", "completed", "critical", 2, D, "documentation/privacy-risk-register.md from the providers' published terms", "", [], None, ""),
    ("sec.provider-answers", "security", "Written answers from ElevenLabs and OpenAI on training, retention, residency, deletion", "awaiting_external", "critical", 3, None, "", "ElevenLabs training on API data is unresolved", ["sec.review"], "security", ""),
    ("sec.legal", "security", "Ghana Data Protection Act 2012 review by a qualified professional", "awaiting_external", "critical", 4, None, "", "Needs a Ghanaian data protection professional", ["sec.review"], "security", ""),
    ("sec.consent", "security", "Caller notice and consent for AI and recording", "not_started", "critical", 3, None, "", "", ["sec.legal"], "security", ""),
    ("sec.retention", "security", "Retention schedule, deletion and export on request", "not_started", "high", 4, None, "", "", ["sec.legal"], "security", ""),
    ("sec.2fa", "security", "Two-factor sign-in", "not_started", "low", 3, None, "", "", [], None, ""),
    ("sec.secrets", "security", "Production secrets management and key rotation procedure", "not_started", "high", 2, None, "", "", [], "security", ""),
    # ---- usage
    ("usage.record", "usage", "Per-call usage and cost estimates saved per business", "completed", "high", 3, T, "tests/api/test_usage.py (isolation, price effectivity, failures) with mutation checks", "", [], None, "Estimates, not invoices. Only voice test calls exist today."),
    ("usage.platform", "usage", "Platform price records and platform-wide totals", "completed", "high", 2, T, "tests/api/test_usage.py (platform admin only)", "", ["usage.record"], None, ""),
    ("usage.budgets", "usage", "Monthly budget caps and alerts per business", "not_started", "medium", 3, None, "", "", ["usage.record"], None, ""),
    ("usage.telephony", "usage", "Telephony cost per call", "not_started", "medium", 2, None, "", "", ["tel.adapter"], None, ""),
    ("usage.billing", "usage", "Subscription plans and billing", "not_started", "medium", 5, None, "", "", ["usage.record"], None, ""),
    # ---- testing
    ("test.backend", "testing", "Offline backend test suite (fakes, no paid calls)", "completed", "high", 3, T, "323 passed, 2 skipped on SQLite; 172 passed on PostgreSQL API suite (run 2026-11-27)", "", [], None, ""),
    ("test.project-dashboard", "testing", "Project progress dashboard for platform administrators", "completed", "medium", 2, T, "tests/api/test_project_tracker.py (11 tests) and a Chromium run: 18 of 18 checks, including 404 for another business and no horizontal scroll at 390 px", "", [], None, ""),
    ("test.e2e", "testing", "Commit the browser end-to-end scripts to the repository", "not_started", "high", 3, None, "", "Scripts exist only in a scratch folder", [], None, ""),
    ("test.ci", "testing", "Continuous integration (tests, type check, lint, build on every push)", "not_started", "high", 3, None, "", "", [], "monitoring", ""),
    ("test.frontend-unit", "testing", "Frontend unit-test runner", "not_started", "medium", 2, None, "", "", [], None, ""),
    ("test.coverage", "testing", "Measure code coverage", "not_started", "low", 1, None, "", "", [], None, ""),
    ("test.load", "testing", "Concurrent-call and load test", "not_started", "medium", 3, None, "", "", ["voice.live-check"], "voice_quality", ""),
    # ---- deployment
    ("dep.hosting", "deployment", "Choose hosting and region", "awaiting_approval", "high", 2, None, "", "Owner decision; affects data residency", [], None, ""),
    ("dep.pipeline", "deployment", "Build and deploy pipeline", "not_started", "high", 3, None, "", "", ["dep.hosting", "test.ci"], None, ""),
    ("dep.backup", "deployment", "Database backups and a tested restore", "not_started", "critical", 3, None, "", "", ["dep.hosting"], "backup", ""),
    ("dep.monitoring", "deployment", "Error tracking, uptime and alerting", "not_started", "high", 3, None, "", "", ["dep.hosting"], "monitoring", ""),
    ("dep.domain-tls", "deployment", "Domain, HTTPS and security headers", "not_started", "high", 2, None, "", "", ["dep.hosting"], None, ""),
]

MILESTONES = [  # (name, phase, description, start, target, reached)
    ("Foundation: accounts, teams, knowledge text, privacy, voice code (offline)", "Foundation", "Built and tested offline.", date(2026, 10, 1), date(2026, 11, 22), True),
    ("Live provider check passes", "Live voice", "Proposed target. Needs the OpenAI and ElevenLabs keys.", date(2026, 11, 23), date(2026, 12, 6), False),
    ("Email live (verified domain)", "Email", "Proposed target. Needs the verified Resend domain.", date(2026, 11, 23), date(2026, 12, 13), False),
    ("Ghanaian-English recognition result", "Live voice", "Proposed target. Needs consented recordings.", date(2026, 11, 30), date(2026, 12, 20), False),
    ("Routing and callbacks (simulated)", "Routing", "Proposed target.", date(2026, 11, 23), date(2026, 12, 20), False),
    ("Telephony pilot with one real transfer", "Telephony", "Proposed target. Needs provider written answers and owner approval.", date(2026, 12, 14), date(2027, 1, 31), False),
    ("Knowledge uploads and AI settings screens", "Product", "Proposed target.", date(2026, 12, 1), date(2027, 1, 15), False),
    ("Privacy and legal gate cleared", "Launch", "Proposed target. Needs provider answers and legal review.", date(2026, 12, 1), date(2027, 1, 31), False),
    ("Production launch readiness", "Launch", "Proposed target.", date(2027, 1, 15), date(2027, 3, 15), False),
]

EXTERNAL = [  # (name, category, owner, detail)
    ("OpenAI API key as a server setting", "awaiting_us", "Owner", "OPENAI_API_KEY"),
    ("ElevenLabs API key and voice id as server settings", "awaiting_us", "Owner", "ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID"),
    ("Resend sending domain verified and API key", "awaiting_us", "Owner", "Add the DNS records, then set EMAIL_DOMAIN_VERIFIED=true"),
    ("Consented Ghanaian-English recordings", "awaiting_us", "Owner", "Consent forms, scripted sentences, at least 8 speakers"),
    ("Telnyx written confirmation", "awaiting_provider", "Telnyx", "Ghana number and rates, streaming, SIP, transfers, concurrency, requirements"),
    ("Africa's Talking written confirmation", "awaiting_provider", "Africa's Talking", "Real-time audio streaming, rates, transfers, requirements"),
    ("Twilio written confirmation", "awaiting_provider", "Twilio", "Ghana number, Media Streams price, requirements"),
    ("ElevenLabs answers on training, retention and deletion", "awaiting_provider", "ElevenLabs", "Questions listed in the privacy risk register"),
    ("OpenAI DPA and zero-retention approval", "awaiting_provider", "OpenAI", "Questions listed in the privacy risk register"),
    ("Ghana Data Protection Act review", "awaiting_provider", "Ghanaian data protection professional", "Items listed in the privacy risk register"),
    ("Telephony provider selection", "awaiting_approval", "Owner", "After the written confirmations"),
    ("Telephony pilot spending cap and number purchase", "awaiting_approval", "Owner", "No spend without approval"),
    ("Hosting choice and region", "awaiting_approval", "Owner", ""),
    ("Provider terms read from public pages", "completed", "Claude", "documentation/privacy-risk-register.md"),
    ("Telephony comparison from public pages", "completed", "Claude", "documentation/telephony-comparison.md"),
]

FINANCE = [  # (label, category, kind, amount, period, state, note)
    ("Live provider check (speech and a short reply)", "api", "estimate", "0.05", "one run", "", "Upper estimate from list prices; OpenAI price not checked"),
    ("Speech recognition evaluation, about 400 clips of 8 seconds", "api", "estimate", "0.20", "one run", "", "3,200 seconds at the listed hourly rate"),
    ("Resend free plan", "email", "estimate", "0", "per month", "", "Free plan limits apply; paid plan from $20 a month"),
]


async def main() -> None:
    factory = make_session_factory(make_engine(Settings()))
    added = {"tasks": 0, "milestones": 0, "external": 0, "finance": 0}
    async with factory() as db:
        have = {t.key: t for t in (await db.execute(select(ProjectTask))).scalars() if t.key}
        for key, module, title, status, prio, weight, kind, ev, blocker, _deps, area, desc in TASKS:
            if key in have:
                continue
            t = ProjectTask(key=key, module=module, title=title, description=desc, status=status, priority=prio, weight=weight, evidence_kind=kind, evidence=ev,
                            blocker=blocker, is_launch=bool(area), launch_area=area, depends_on=[],
                            completed_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc) if status == "completed" else None)
            db.add(t)
            have[key] = t
            added["tasks"] += 1
        await db.flush()
        for key, *_rest in TASKS:  # dependencies are resolved to ids only for tasks created in this run
            row = next(r for r in TASKS if r[0] == key)
            t = have[key]
            if not t.depends_on:
                t.depends_on = [str(have[k].id) for k in row[9] if k in have]
        names = {m.name for m in (await db.execute(select(ProjectMilestone))).scalars()}
        for name, phase, desc, start, target, reached in MILESTONES:
            if name not in names:
                db.add(ProjectMilestone(name=name, phase=phase, description=desc, start_date=start, target_date=target,
                                        reached_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc) if reached else None))
                added["milestones"] += 1
        ext = {e.name for e in (await db.execute(select(ProjectExternal))).scalars()}
        for name, cat, owner, detail in EXTERNAL:
            if name not in ext:
                db.add(ProjectExternal(name=name, category=cat, owner=owner, detail=detail))
                added["external"] += 1
        fin = {f.label for f in (await db.execute(select(ProjectFinance))).scalars()}
        for label, cat, kind, amount, period, state, note in FINANCE:
            if label not in fin:
                db.add(ProjectFinance(label=label, category=cat, kind=kind, amount_micro_usd=int(float(amount) * 1_000_000), period=period, state=state, note=note))
                added["finance"] += 1
        await db.commit()
    print("Added:", added)


if __name__ == "__main__":
    asyncio.run(main())
