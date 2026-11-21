# Frontend API contract

The frontend (`frontend/`) was built before the backend implemented anything, so it targets the contract below. **Status (2026-11-20):** the endpoints below are implemented in `backend/app/api/v1/` and tested (SQLite and PostgreSQL 16, plus a browser run of the real frontend against the real API). Notes on what is real and what is not are in "Implementation status" at the end. All routes sit under `NEXT_PUBLIC_API_BASE_URL` + `NEXT_PUBLIC_API_PREFIX` (default `http://localhost:8000/api/v1`). Every integration point is isolated in `src/lib/auth.ts` and `src/features/dashboard/api.ts`, so changing a route or shape touches one file.

## Conventions the frontend relies on

- **Session:** an httpOnly, `SameSite=Lax` cookie set by login/register. The frontend sends `credentials: "include"` and never sees or stores a token. In production use `Secure`, and serve frontend and API from the same site (or configure CORS with credentials for the exact frontend origin, not `*`).
- **Tenant:** the backend derives the business from the session. After a user with several businesses switches, the frontend sends `X-Business-Id`; the backend **must verify** the user may act for that business (403 if not). The frontend never enforces tenancy.
- **Errors:** FastAPI-style bodies are understood: `{"detail": "msg"}` or `{"detail": [{"loc": ["body","email"], "msg": "..."}]}` (422 field errors map onto form fields). Status handling: 401 → session expired, 403 → permission denied, 404 → "not available yet", 422 → field errors, 5xx → retry.
- **Timestamps:** ISO 8601 UTC strings.

## Authentication

| Method | Path | Request | Success |
|---|---|---|---|
| POST | `/auth/login` | `{email, password}` | 200 `SessionResponse` + session cookie. 401 on bad credentials. |
| POST | `/auth/register` | `{business_name, full_name, email, password}` | 201 `SessionResponse` + cookie. 409 if email exists, 422 for field errors. Creates the business, default roles and the first Administrator. |
| POST | `/auth/logout` | none | 204, clears cookie. |
| GET | `/auth/me` | none | 200 `SessionResponse`; 401 if no session. Called on every page load. With `X-Business-Id`, returns the session for that business. |
| POST | `/auth/forgot-password` | `{email}` | 204 regardless of whether the account exists (no account enumeration). |

`SessionResponse = { user: {id, email, full_name, status, role: {id, name}}, business: {id, name, slug}, businesses?: [{id, name, slug}] }` (`businesses` only for multi-business accounts; it enables the switcher).

The registration form has **no phone field**: `schema.sql` has no phone column on `businesses` or `users`. Add the column and the field together if wanted.

## Dashboard

| Method | Path | Returns |
|---|---|---|
| GET | `/dashboard/kpis` | `{total_calls, total_sms_conversations, active_cases, pending_department_requests, ai_resolution_rate, average_response_seconds}`, each `{value: number\|null, trend?: {change_pct, period_label}}`. `null` = no data (shown as "No data yet"). Rate is 0–100; response time in seconds. |
| GET | `/dashboard/case-overview` | `{open, in_progress, waiting_department, resolved}` |
| GET | `/dashboard/department-activity` | `{items: [{id, name, open_cases, pending_requests}], total, page, page_size}` |
| GET | `/conversations?page_size=20&sort=-started_at` | `{items: [{id, channel, status, customer_name, summary, started_at}], total, page, page_size}`. Channel is one of `whatsapp, sms, email, phone, web_chat, other`. |
| GET | `/agents?page_size=10` | `{items: [{id, name, status, channels[], last_activity_at, configured}], ...}`. `channels`, `last_activity_at` and `configured` are derived by the backend. |
| GET | `/notifications/summary` | `{unread_total, unread_conversations, items: [{id, title, body, href, created_at, read}]}`. `unread_conversations` drives the Communication Center badge. |

## Gaps between the database schema and what the UI needs

1. **"Waiting for department response"** (case overview, brief §8D): `cases.status` only has `waiting_customer`. Add a `waiting_department` status, or define how the count is derived.
2. **Calls vs SMS:** `conversations.channel` covers this (`phone`, `sms`), but "Total Calls" and "AI Resolution Rate" need definitions (what counts as AI-resolved), so the backend must compute them.
3. **Search:** the header search only finds app pages. Customer/case/conversation search needs a `GET /search?q=` endpoint, which is not specified yet.
4. **Business switching** assumes users can belong to several businesses. `users.business_id` is a single column, so this needs a membership table first; until then `businesses` is simply omitted and no switcher appears.
5. **Password reset** needs a token table and an email provider.

## Security notes for the backend implementer

Enforce authorization and tenant isolation on every endpoint. The frontend route guard is a usability feature only. Hash passwords with argon2 or bcrypt. Rate-limit login, register and forgot-password. Set CORS to the exact frontend origin with credentials. Use CSRF protection for cookie-authenticated state-changing requests (e.g. a double-submit token or a custom header check), since the session is a cookie.

## Implementation status (2026-11-20)

Implemented and tested: `/auth/login|register|logout|me|forgot-password`, `/dashboard/kpis|case-overview|department-activity`, `/conversations`, `/agents`, `/notifications/summary`, `/health`.

- **Sessions** are server-side rows (`auth_sessions`, migration 0002). The cookie holds a random token; only its SHA-256 is stored. Logout deletes the row, so a copied cookie stops working. Default lifetime 7 days (`SESSION_TTL_HOURS`), no sliding renewal yet.
- **CSRF:** every POST/PUT/PATCH/DELETE must carry an `Origin` (or `Referer`) from `CORS_ORIGINS`, otherwise 403. The cookie is also `SameSite=Lax`, `HttpOnly`, and `Secure` when `ENVIRONMENT=production`.
- **Tenancy:** the business comes from the session. A different `X-Business-Id` is refused with 403 (users have one business until a membership table exists, so `businesses` is not returned and no switcher appears). Every dashboard query filters by that business; tests seed two businesses and assert nothing crosses, including a deliberately corrupt cross-tenant foreign key.
- **Passwords:** argon2id; login does the same work for unknown emails and returns one message for every failure. Registration returns 409 for a taken email (as the contract specifies), which does reveal that the email is registered.
- **Rate limit:** login, register and forgot-password are limited per client address (and email) in process memory. This is per worker and trusts the socket address; behind a proxy or several workers it needs Redis and proper forwarded-address handling.
- **KPIs:** `ai_resolution_rate` and `average_response_seconds` return `null` ("No data yet") until they are defined and recorded. `resolved` counts only `resolved` cases. An agent is `configured` when `config.instructions` is non-empty.
- **Not implemented:** password reset (no token table or email provider; the endpoint accepts the request and sends nothing), notifications (always empty), search endpoint, business switching, user/employee/department/customer/case CRUD, role-based permission checks on endpoints (all roles can read the dashboard), audit log, email verification, account lockout, session listing/revocation.
- **Database:** `backend/migrations/0001_initial.sql` is your schema unchanged; `0002` adds `auth_sessions` and the `waiting_department` case status. Both were applied to a real PostgreSQL 16 and the API tests ran against it with `TEST_DATABASE_URL`.

## Customers and cases (added 2026-11-20; the frontend has no screens for these yet)

| Method | Path | Notes |
|---|---|---|
| POST / GET | `/customers` | create (`full_name`, optional `email`, `phone`, `external_ref`); list with `q` (name, email, phone, reference; `%` and `_` are literal), `page`, `page_size` ≤ 100 |
| GET / PATCH | `/customers/{id}` | PATCH sends only changed fields; `null` clears email/phone/reference |
| POST / GET | `/cases` | create (`customer_id`, `title`, optional `description`, `priority`, `department_id`, `conversation_id`); list filters `status`, `priority`, `department_id`, `assigned_employee_id`, `customer_id`, `q` |
| GET / PATCH | `/cases/{id}` | PATCH: `title`, `description`, `priority`, `status`, `department_id`, `assigned_employee_id` (`null` unassigns), `resolution_notes` |
| GET | `/cases/{id}/events` | append-only history: created, status_changed, assigned, updated; who (`user` / `ai`), when, what changed |

Rules enforced by the backend: every id must belong to the caller's business (otherwise 404 or 422, never confirming another business's record exists); assignees must be active employees; a conversation must belong to the case's customer. Status flow: open, in_progress, waiting_customer and waiting_department move freely among themselves and to resolved; resolving needs resolution notes; resolved can be reopened or closed; closed is final (409). History records which fields changed, not their text. Permissions: `customers:read|write`, `cases:read|write` (write includes read, `*` is everything). Default roles: Administrator `*`; Manager and Employee read and write cases and customers; Auditor-style read-only roles work but there is no endpoint to create roles or users yet. Customers are never merged automatically, not even when phone numbers match.

Not done: a human-readable case reference number (cases are identified by UUID), notes separate from the history, SLA timers, notifications on assignment, concurrent-edit protection (last write wins), employee/department CRUD (assignment works only for employees that already exist in the database).

## Departments and employees (added 2026-11-20; no frontend screens yet)

| Method | Path | Notes |
|---|---|---|
| POST / GET | `/departments` | name 2–100 chars, unique per business ignoring case (409); list includes `employee_count` and `open_cases` |
| GET / PATCH / DELETE | `/departments/{id}` | DELETE is refused (409) while any employee or case still points at it, so staff and cases are never silently detached |
| POST / GET | `/employees` | `full_name`, optional `email`, `phone`, `job_title`, `department_id`, `status` (`active`, `on_leave`, `inactive`); list filters `q`, `department_id`, `status` |
| GET / PATCH | `/employees/{id}` | `null` clears email/phone/title/department. Employees are deactivated, never deleted, because cases refer to them |

Rules: a department must belong to the same business (422 otherwise); setting an employee `inactive` is refused (409) while they have open cases (reassign first), `on_leave` is allowed, and only `active` employees can be assigned new cases. `has_login` says whether the employee is linked to a user account, and staff logins are created by invitation (see "Staff accounts" below). Permissions: `departments:read|write`, `employees:read|write`. Defaults: Administrator everything; Manager writes both; Employee reads both.

Not done: department managers/heads, employee working hours or availability (needed for call routing), bulk import.

## Frontend screens (2026-11-20)

Built and checked in a real browser against the real API on PostgreSQL 16 (25 scripted checks, run by hand; the script is not in the repo): `/cases` (list, filters, search, create), `/cases/{id}` (details, status/priority/department/assignee/resolution notes, history), `/customers` (list, search, add, edit), `/departments` (list, add, edit, delete), `/employees` (list, filters, add, edit).

- `GET /auth/me` and login now include `user.role.permissions` (e.g. `["*"]`, `["cases:read","customers:read"]`). The screens use it only to hide buttons the role cannot use; every action is still checked by the backend. Users without read access to a page get a "Permission denied" message, but the sidebar still lists every page.
- Pickers (department, assignee) load up to 100 departments/employees; a business with more than 100 would need search-as-you-type pickers.
- Not built: customer detail page, a customer's case list, editing a case's title or description, creating employee logins, bulk actions, notifications, per-column sorting. The history shows "Team member" rather than a name because the API returns only the user id.
- The case-status choices offered in the UI mirror the backend's rules; if they ever disagree the backend wins and the UI shows its 409 message.

## Staff accounts (added 2026-11-21)

Migration `0004_user_invites.sql` (apply after 0003). There is no email provider, so an invitation is a one-time link that the administrator copies and sends themselves.

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/users`, `/roles`, `/users/invites` | `users:read` | pending invitations only; the token is never listed |
| POST | `/users/invites` | `users:write` | `{email, role_id, employee_id?}` returns `{id, email, token, expires_at}`. **The token is returned once**; only its SHA-256 is stored. Valid 7 days |
| DELETE | `/users/invites/{id}` | `users:write` | withdraw; the link stops working |
| PATCH | `/users/{id}` | `users:write` | `role_id` and/or `status` (`active` / `disabled`) |
| POST | `/auth/invite-info` | public, rate-limited | `{token}` returns email, business name, role name; 404 for any bad token |
| POST | `/auth/accept-invite` | public, rate-limited | `{token, password (min 10), full_name?}` creates the user, links the employee if the invitation named one, starts a session |

Rules: roles and employees must belong to the inviter's business (422); inviting an email that already has an account anywhere or a pending invitation here gives one identical 409, so another business's accounts are not revealed; an expired invitation can be replaced; tokens are single use. You cannot change your own role or disable yourself; the last active administrator (a role holding `*`) cannot be demoted or disabled; disabling deletes the user's sessions, so they are signed out on their next request; role changes apply on the next request. `users:*` is held only by Administrator by default.

Frontend: `/settings/team` (people, role selector, enable/disable, pending invitations, invite dialog that shows the link once) and public `/accept-invite`. The link carries the token in the URL fragment (`#token=...`), which browsers never send to servers, and the page removes it from the address bar after reading it. Checked in a real browser against PostgreSQL 16 (20 scripted checks, not in the repo) and by 9 backend tests (mutation-checked: removing the tenant filter, the self guard, the last-admin guard or session revocation each makes a test fail).

Not done: sending the invitation by email, password reset, creating custom roles or editing role permissions, an audit log of staff changes, a customer-facing "your sessions" screen. Anyone who holds the link can accept it until it expires or is withdrawn, so send it over a channel you trust.

## Knowledge base (added 2026-11-21)

Migration `0005_knowledge_base.sql` (apply after 0004). Approved text the voice assistant may quote: opening hours, policies, procedures.

| Method | Path | Permission | Notes |
|---|---|---|---|
| POST / GET | `/knowledge` | `knowledge:write` / `:read` | `title`, optional `category`, `content` (3–50,000 chars), `status` (`published` default, or `archived`). List filters `q` (title, category), `status`; list omits `content` |
| GET / PATCH / DELETE | `/knowledge/{id}` | read / write | editing `content` re-splits it into chunks; DELETE removes the document and its chunks |
| GET | `/knowledge/search?q=` | `knowledge:read` | shows what the assistant would find for a question (top 3 passages), so staff can check their documents |

How the assistant uses it: `DatabaseBusinessGateway` now offers `search_knowledge`. It searches only the caller's business and only **published** documents, and returns at most three passages of up to 900 characters each, so only the relevant text reaches the AI provider. When nothing matches, the tool result tells the model not to guess and to offer a team member. Search is keyword-based (documents are split into ~700-character chunks; terms are matched case-insensitively and scored by how many appear, how often, and in the title). There are no embeddings: that needs an embeddings provider, which has not been approved, and keyword search keeps document text on our own database.

Data protection: documents are business-written, tenant-scoped rows; other businesses' documents are never returned (404 / empty). The editor warns against storing passwords or card numbers; redaction in `redact_for_provider` is a safety net only. Text in a document is treated by the model as data to quote, not instructions, but a malicious or careless document can still steer answers, so only trusted staff should have `knowledge:write` (Manager has it by default; Employee has read). New businesses get these defaults; **existing businesses' roles are unchanged**, so add `knowledge:read`/`write` to their roles if needed. Frontend: `/knowledge` (list, search, status filter, add/edit with `.txt`/`.md` import read in the browser, delete, and a "Test a question" panel). Checked in a real browser (11 scripted checks, not in the repo) and by 6 backend tests mutation-checked for the tenant filters and the published-only rule; all API tests also pass on PostgreSQL 16.

Not done: PDF/Word import (paste the text instead), semantic search, per-document versions or approval workflow, language detection per document (Twi, Ewe and Ga remain unsupported by the voice layer), sorting by relevance across more than 300 candidate chunks, and the voice pipeline is still not wired to the API, so the assistant cannot yet use this over a live call.

## Live voice test call (added 2026-11-21; offline-tested only)

`WS /api/v1/voice/test-call[?agent_id=]` and `GET /api/v1/voice/status`, permission `voice:use` (Administrator by default through `*`; no other default role has it).

Wiring: `services/voice/call_runner.py` runs one call (audio in, ElevenLabs speech-to-text, `ConversationManager`, text-to-speech, audio out, barge-in, hand-over when speech recognition fails, a watchdog for silence and maximum length). `services/voice/stack.py` builds the real providers. `api/v1/voice.py` is the WebSocket transport.

Protocol: the client sends binary PCM signed 16-bit little-endian, 16 kHz, mono (frames over 32 KB are dropped) and `{"type":"end"}` to hang up. The server sends JSON events (`ready`, `state`, `transcript` for both speakers, `interrupted`, `handover`, `error` with a code) and binary audio in `output_format` (default `pcm_16000`).

Safety: the handshake is refused (HTTP 403 before accept) unless `Origin` is in `CORS_ORIGINS`, because browsers attach cookies to cross-site WebSocket handshakes and the CSRF middleware does not cover WebSockets. The session cookie, its business and `voice:use` are checked; another business's `agent_id` looks the same as a missing one; per-business concurrent and per-minute call limits apply. **Live voice is off by default**: it needs `VOICE_LIVE_ENABLED=true`, `OPENAI_API_KEY`, `ELEVENLABS_API_KEY` and a voice (`ELEVENLABS_DEFAULT_VOICE_ID` or the agent's `config.voice_id`), because it calls paid providers. `/voice/status` lists what is missing by name only. `VOICE_DISABLED_PROVIDERS=["openai"]` switches a provider off at startup. Nothing is stored: the transcript lives in memory for the call and the log line at the end holds counts only. A test call is not saved as a conversation because that needs an identified customer, so the assistant can search the knowledge base but cannot log cases on a test call (the tool refuses honestly).

Checked with fake speech, reasoning and voice providers (8 tests, mutation-checked for the origin check, permission check, agent tenancy and cleanup; 220 pass on SQLite, 81 API tests on PostgreSQL 16). **Nothing has been run against live OpenAI or ElevenLabs, there is no browser microphone page, and there is no telephony.** Real-world behaviour (latency, echo, accents, the ElevenLabs messages the adapters assume) is unverified until an approved live test. The browser must use echo cancellation, otherwise the assistant's own voice will be heard as the customer and trigger barge-in. Debug logging of SQL drivers records query parameters, which can include text derived from calls; do not enable it in production. The per-business provider switch is process-wide today (a runtime per-business switch needs a table).

## Privacy controls and audit log (added 2026-11-21)

Migration `0006_privacy_and_audit.sql` (apply after 0005).

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET / PATCH | `/privacy` | `privacy:read` / `privacy:write` | `ai_providers_enabled`, `redact_contact_details` (per business); `redact_secrets` is platform-level and read-only. No row means defaults: AI on, contact masking from the platform setting |
| GET | `/audit` | `audit:read` | newest first; paginated |

Both permissions are Administrator-only by default (`*`). **Enforced today:** with `ai_providers_enabled` off the voice test call is refused (`ai_disabled_by_business`) before any provider is contacted, and `redact_contact_details` is carried in the session into every request to the reasoning provider (a per-business override of the platform default; checked in tests). The audit log (`audit_events`, append-only by a PostgreSQL trigger, checked on PostgreSQL 16) records privacy changes, invitations created, withdrawn and accepted, and role or status changes, as field names and ids with the actor; never message text, passwords or tokens. It does not yet record customer, case, knowledge or employee edits, sign-ins, or reads.

Deliberately **not** offered: transcript or recording retention settings and recording consent. The platform stores no transcripts or audio today, so a retention control would do nothing; add them together with transcript storage. Not done: a provider switch for the future telephony path, vendor agreements or zero-data-retention terms with OpenAI and ElevenLabs, deletion/export of a customer's data on request, a legal review under Ghana's Data Protection Act, 2012 (Act 843). Frontend: `/settings/privacy` (two switches, the secrets note and the activity log), checked in a real browser (7 scripted checks, not in the repo) and by 5 backend tests (mutation-checked for the audit tenant filter, the voice refusal and audit writing; 87 API tests pass on PostgreSQL 16, 225 on SQLite).

## Browser microphone test page (added 2026-11-21)

`/communication/voice-test` (sidebar: Communication Center, Voice test), permission `voice:use`. It asks `/voice/status` first; if live voice is not switched on it shows what the server operator must set instead of a Start button.

How it works (`src/lib/voice/`): `getUserMedia` with echo cancellation, noise suppression and auto gain; an AudioWorklet (`public/pcm-capture-worklet.js`) hands microphone blocks to the page; `Downsampler` converts to 16 kHz by averaging; `Framer` sends 100 ms frames (3,200 bytes) of PCM16 over the WebSocket; assistant audio (`pcm_<rate>` only; other formats are refused with a message) is decoded and scheduled gaplessly with the Web Audio API. On the server's `interrupted` event the page stops everything playing and discards what is queued. Leaving the page, pressing End call, or the server closing the socket releases the microphone and the audio contexts. The page shows a microphone level meter, the live transcript of both sides, the assistant's state, and clear messages for a refused or missing microphone, a refused call (permission or expired session), or a server-reported error code.

Checked three ways. (1) The pure audio code (resampling, framing, little-endian conversion, odd-byte chunk splits) with `node --experimental-transform-types frontend/scripts/pcm.check.ts`. (2) A real Chromium with a fake microphone against the real API and WebSocket with **fake** speech, reasoning and voice providers: 14 scripted checks (frames arrive in 100 ms pieces, transcripts show, the assistant's audio plays, barge-in stops playback at once, ending or leaving stops the stream and the server side closes, a second call works, the business AI switch is respected, a blocked microphone is explained, phone layout). The barge-in check was confirmed to fail when the stop-playback line is removed. The browser script and the fake-provider server are not in the repo. (3) The earlier backend tests.

Not verified: how it sounds and feels with real OpenAI and ElevenLabs (latency, accuracy, the true audio format the live provider returns), Safari and Firefox (only Chromium was run), echo on speakers (use headphones), and very long calls. The page is for staff testing; there is no customer-facing web call widget or telephony.

## Branding (2026-11-21)

The product is **KASORA AI** (`APP_NAME` in `frontend/src/lib/config.ts`; page titles read "<page> · KASORA AI"). The logo mark (hub with five nodes, from the supplied icon design) is the `KasoraMark` component, drawn in `currentColor` so it follows light and dark surfaces; the intro animation (lines draw, nodes pop in, hub breathes) runs on the sign-in and register pages and is skipped for visitors who prefer reduced motion. Icons: `src/app/icon.svg` adapts to the browser's light or dark scheme; `apple-icon.png`, `favicon.ico`, `public/icon-192.png` and `icon-512.png` are static light versions (generated from the same drawing), and `manifest.webmanifest` names the app for "install". "Control Center" is still used in some descriptive text as the name of the admin area. Not done: a wordmark or typeface for KASORA, brand colours beyond the existing navy and teal theme, and emails or documents that carry the logo.
