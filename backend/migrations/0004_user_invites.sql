-- One-time invitations for staff logins. Only a hash of the token is stored.
-- Apply after 0003:  psql -d your_database -f migrations/0004_user_invites.sql
BEGIN;

CREATE TABLE user_invites (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id  UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    email        TEXT NOT NULL,                                   -- stored lower-cased
    role_id      UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    employee_id  UUID REFERENCES employees(id) ON DELETE SET NULL, -- link the new login to this employee
    token_hash   TEXT NOT NULL UNIQUE,
    invited_by   UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ NOT NULL,
    accepted_at  TIMESTAMPTZ
);
CREATE INDEX user_invites_business_idx ON user_invites (business_id);
CREATE UNIQUE INDEX user_invites_pending_email ON user_invites (business_id, email) WHERE accepted_at IS NULL;

COMMIT;
