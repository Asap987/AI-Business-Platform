-- Email verification. Existing accounts stay NULL (unverified) because nothing proved their address; they can verify
-- from the banner once email is enabled. Invited staff are marked verified when they accept the invitation.
-- Apply after 0007:  psql -d your_database -f migrations/0008_email_verification.sql
BEGIN;

ALTER TABLE users ADD COLUMN email_verified_at TIMESTAMPTZ;

CREATE TABLE email_verifications (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL,
    used_at     TIMESTAMPTZ
);
CREATE INDEX email_verifications_user_idx ON email_verifications (user_id);

COMMIT;
