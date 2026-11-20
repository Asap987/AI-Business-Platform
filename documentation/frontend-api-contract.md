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
