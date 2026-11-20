-- Server-side login sessions and the "waiting_department" case status.
-- Apply after 0001_initial.sql:  psql -d your_database -f migrations/0002_auth_sessions_and_case_status.sql
BEGIN;

CREATE TABLE auth_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL UNIQUE,           -- sha256 of the cookie value; the token itself is never stored
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX auth_sessions_user_idx ON auth_sessions (user_id);
CREATE INDEX auth_sessions_expiry_idx ON auth_sessions (expires_at);

ALTER TABLE cases DROP CONSTRAINT cases_status_check;
ALTER TABLE cases ADD CONSTRAINT cases_status_check
    CHECK (status IN ('open', 'in_progress', 'waiting_customer', 'waiting_department', 'resolved', 'closed'));

COMMIT;
