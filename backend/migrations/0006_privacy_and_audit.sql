-- Per-business privacy controls for AI providers, and an append-only audit log of sensitive changes.
-- Apply after 0005:  psql -d your_database -f migrations/0006_privacy_and_audit.sql
BEGIN;

CREATE TABLE business_privacy (
    business_id             UUID PRIMARY KEY REFERENCES businesses(id) ON DELETE CASCADE,
    ai_providers_enabled    BOOLEAN NOT NULL DEFAULT TRUE,   -- FALSE: no customer data may be sent to OpenAI/ElevenLabs
    redact_contact_details  BOOLEAN NOT NULL DEFAULT FALSE,  -- mask emails and phone numbers before text reaches the AI
    updated_by              UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_events (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id   UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action        TEXT NOT NULL,
    detail        JSONB NOT NULL DEFAULT '{}'::jsonb,   -- field names and ids, never message text or secrets
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX audit_events_business_idx ON audit_events (business_id, created_at DESC);

CREATE OR REPLACE FUNCTION audit_events_immutable() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER audit_events_no_update BEFORE UPDATE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_immutable();

COMMIT;
