-- Append-only history of what happened to each case (who, what, when).
-- Apply after 0002:  psql -d your_database -f migrations/0003_case_events.sql
BEGIN;

CREATE TABLE case_events (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id   UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    case_id       UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,  -- NULL when the AI assistant or system acted
    actor_kind    TEXT NOT NULL DEFAULT 'user' CHECK (actor_kind IN ('user', 'ai', 'system')),
    kind          TEXT NOT NULL,                                -- created, status_changed, assigned, updated, ...
    detail        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX case_events_case_idx ON case_events (case_id, created_at);
CREATE INDEX case_events_business_idx ON case_events (business_id);

-- Nobody, including the application role, may rewrite history.
CREATE OR REPLACE FUNCTION case_events_immutable() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'case_events is append-only';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER case_events_no_update BEFORE UPDATE ON case_events
    FOR EACH ROW EXECUTE FUNCTION case_events_immutable();

COMMIT;
