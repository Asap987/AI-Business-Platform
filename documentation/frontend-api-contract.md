# Frontend API contract

The frontend (`frontend/`) was built before the backend implemented anything, so it targets the contract below. **None of these endpoints exist yet.** Until they do, the app shows honest "not available" states instead of data. All routes sit under `NEXT_PUBLIC_API_BASE_URL` + `NEXT_PUBLIC_API_PREFIX` (default `http://localhost:8000/api/v1`). Every integration point is isolated in `src/lib/auth.ts` and `src/features/dashboard/api.ts`, so changing a route or shape touches one file.

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
