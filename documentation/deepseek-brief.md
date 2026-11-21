# Brief for DeepSeek: KASORA AI, round 1

You are joining an existing, working project. Read this whole brief, then read the files it points to **before writing code**. Match the existing patterns; do not invent new ones.

## Project

KASORA AI (repo `Asap987/AI-Business-Platform`) is a multi-tenant SaaS: businesses get an AI assistant that answers customer calls and messages, logs cases and routes them to departments. Backend: Python 3.13, FastAPI, SQLAlchemy 2 async, PostgreSQL (SQLite in tests), pytest. Frontend: Next.js (app router), React, TypeScript strict, Tailwind v4, lucide-react.

Start from branch `feature/frontend-shell-and-voice-foundation`. **Create your own branch from it** (one per task, e.g. `deepseek/customer-detail`). Never push to `main` or to the feature branch. Open a pull request into `feature/frontend-shell-and-voice-foundation` when done.

Read first: `README.md`, `documentation/frontend-api-contract.md` (every endpoint, rule and known gap), `frontend/AGENTS.md`.

## Non-negotiable rules

1. **Tenant isolation is the most important property.** The business always comes from the signed-in session (`Principal.business_id` in `backend/app/api/v1/deps.py`), never from the request body or URL. Every database query on tenant data filters by that business. Another business's id answers 404, never "forbidden" and never the data.
2. Every endpoint has a permission check via `require("<permission>")`. The frontend hides buttons with `usePermission`/`can()`, but that is for convenience only; the backend enforces.
3. No API keys, passwords or secrets in code or logs. No new AI or speech providers. Do not invent API endpoints or library methods: if you are unsure something exists, check the code or say so.
4. Do not touch: `backend/app/api/v1/auth.py`, `deps.py`, `backend/app/core/security.py`, `backend/app/services/voice/**`, `backend/app/api/v1/privacy.py`, `team.py`, `voice.py`, and existing migrations `0001`-`0006`. If a task seems to need a change there, stop and ask.
5. New database migrations must be numbered **0100 or higher** (e.g. `0100_...sql`) so they never clash with mine. Add the matching SQLAlchemy model in `backend/app/database/models/tables.py`.
6. Do not claim something works unless you ran it. State exactly what you ran and what you did not.

## Definition of done (all must pass, paste the output)

Frontend, from `frontend/`: `npx tsc --noEmit`, `npm run lint`, `npm run build`.
Backend, from `backend/` (always run from this folder): `python -m pytest`.
New backend endpoints need tests using **two businesses** (see `backend/tests/api/test_customers_cases.py` helpers `two`, `add_user`, `login`, and `test_knowledge.py` for the style) proving: it works, a user of the other business gets 404, and a user without the permission gets 403. Prove the tests can fail: temporarily remove the business filter and confirm a test goes red, then restore it.

## Task A: Customer detail page (frontend only, no backend change)

Route `/customers/[id]`. Today `/customers` lists customers (`frontend/src/features/customers/CustomersView.tsx`) but a customer has no page of its own.

Build `frontend/src/features/customers/CustomerDetailView.tsx` and `frontend/src/app/(dashboard)/customers/[id]/page.tsx`, copying the structure of `features/cases/CaseDetailView.tsx` and `app/(dashboard)/cases/[id]/page.tsx`.

- Load the customer with `useApiResource<Customer>("/customers/" + id)`. Show name, email, phone, external reference, created date. A missing or other-business id shows "Customer not found" (see how `CaseDetailView` handles the not-found error via `ResourceView`/`ErrorMessage`).
- An **Edit** button (only if `usePermission("customers:write")`) opens the same edit form the list uses. Reuse it: extract the customer form from `CustomersView.tsx` into a shared component rather than duplicating it, and make sure the list still works.
- Below the details, show **this customer's cases**: `GET /cases?customer_id=<id>&page=&page_size=20`. Reuse the table/columns/filters from `features/cases/CasesView.tsx` by adding an optional `customerId` prop to it (when set: add the filter, hide the customer column and the customer filter). A "New case" button pre-selects this customer (see `CaseForm.tsx`).
- In `CustomersView.tsx` make each customer name a link to `/customers/<id>`.
- Types are in `frontend/src/types/org.ts`; API helper is `frontend/src/lib/api.ts`.
- Mobile (390 px wide) must not scroll horizontally. Keyboard and screen-reader labels like the existing screens.

## Task B: Hide sidebar items the user's role cannot use (frontend only)

`frontend/src/lib/constants.ts` defines the navigation; `frontend/src/lib/utils.ts` has `can(permissions, needed)`; `usePermission` is in `frontend/src/hooks/usePermission.ts`.

- Add an optional `permission?: string` to each nav item and set it (e.g. Customers `customers:read`, Cases `cases:read`, Knowledge Base `knowledge:read`, Departments `departments:read`, Employees `employees:read`, Settings > Team `users:read`, Settings > Privacy `privacy:read`, Voice test `voice:use`). Items with no permission stay visible to everyone.
- Filter the sidebar and the header page-search by it. Pages must still show their own "Permission denied" state if opened by URL.
- Do not change what the backend allows.

## Task C: Settings, Profile and Business (small backend + frontend)

Routes exist at `frontend/src/app/(dashboard)/settings/profile` and `.../business` as placeholders.

Backend, in a **new file** `backend/app/api/v1/settings.py` (register it in `backend/app/main.py` next to the other routers):
- `PATCH /api/v1/profile` body `{full_name}` (2-120 chars, trimmed). Changes only the **signed-in user's own** name. No other field. Permission: any signed-in user (use `current_principal`).
- `PATCH /api/v1/business` body `{name}` (2-120 chars, trimmed). Changes the signed-in user's business name only. Permission `business:write` (Administrator has it through `*`). Record it in the audit log with `from app.services import audit; audit.record(db, p.business_id, p.user.id, "business.updated", changed=["name"])` before the commit.
- Both return the same session shape as `GET /api/v1/auth/me` (see `_session_response` in `auth.py`; import it, do not edit `auth.py`).
- Tests as described above, including "a user cannot change another user's name" (there is no id parameter, so show that the other user's name is unchanged) and 403 for a role without `business:write`.

Frontend:
- Profile page: shows name and email (email read-only), a form to change the name. After saving, the header and sidebar should show the new name: look at how `AuthProvider` (`frontend/src/providers/AuthProvider.tsx`) holds the session and add a small method to refresh it rather than reloading the page.
- Business page: shows business name; an Administrator-only form to rename it (hide with `usePermission("business:write")`, the backend enforces).
- Follow the form patterns in `features/team/TeamView.tsx` and `features/knowledge/KnowledgeView.tsx` (validation messages, `errorText`, `FormError`, loading states).
- **Do not build password change.** That belongs to the authentication code, which is off limits.

## How to report back

For each task: the branch name, a list of files changed, the pasted output of every command in "Definition of done", anything you could not do or are unsure about, and any rule above you think should change. Keep pull requests small: one task per pull request. I will review each one, including deliberately breaking the tenant filters to confirm your tests catch it, before it is merged.
