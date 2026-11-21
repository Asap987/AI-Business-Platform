-- Single-use, expiring password reset tokens. Only a SHA-256 digest of the token is stored.
-- Apply after 0006:  psql -d your_database -f migrations/0007_password_resets.sql
BEGIN;

CREATE TABLE password_resets (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL,
    used_at     TIMESTAMPTZ
);
CREATE INDEX password_resets_user_idx ON password_resets (user_id);

COMMIT;
