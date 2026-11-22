-- Internal project tracker. Platform-level (no business_id): only users listed in PLATFORM_ADMIN_USER_IDS can reach it.
-- Apply after 0009:  psql -d your_database -f migrations/0010_project_tracker.sql
BEGIN;

CREATE TABLE project_tasks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key           TEXT UNIQUE,
    module        TEXT NOT NULL,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'not_started',
    priority      TEXT NOT NULL DEFAULT 'medium',
    weight        INTEGER NOT NULL DEFAULT 1 CHECK (weight BETWEEN 1 AND 10),
    start_date    DATE,
    deadline      DATE,
    blocker       TEXT NOT NULL DEFAULT '',
    notes         TEXT NOT NULL DEFAULT '',
    depends_on    JSONB NOT NULL DEFAULT '[]',
    evidence_kind TEXT,
    evidence      TEXT NOT NULL DEFAULT '',
    is_launch     BOOLEAN NOT NULL DEFAULT FALSE,
    launch_area   TEXT,
    completed_at  TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by    UUID,
    CHECK (status <> 'completed' OR (evidence_kind IS NOT NULL AND length(evidence) >= 10))
);
CREATE INDEX project_tasks_module_idx ON project_tasks (module);

CREATE TABLE project_milestones (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    phase       TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    start_date  DATE,
    target_date DATE NOT NULL,
    reached_at  TIMESTAMPTZ,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE project_external (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT NOT NULL,
    category   TEXT NOT NULL,
    owner      TEXT NOT NULL DEFAULT '',
    detail     TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE project_finance (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    label            TEXT NOT NULL,
    category         TEXT NOT NULL,
    kind             TEXT NOT NULL,
    amount_micro_usd BIGINT NOT NULL DEFAULT 0,
    period           TEXT NOT NULL DEFAULT '',
    state            TEXT NOT NULL DEFAULT '',
    note             TEXT NOT NULL DEFAULT '',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE project_test_runs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ran_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    source       TEXT NOT NULL DEFAULT 'pytest',
    commit       TEXT NOT NULL DEFAULT '',
    total        INTEGER NOT NULL DEFAULT 0,
    passed       INTEGER NOT NULL DEFAULT 0,
    failed       INTEGER NOT NULL DEFAULT 0,
    skipped      INTEGER NOT NULL DEFAULT 0,
    duration_s   DOUBLE PRECISION NOT NULL DEFAULT 0,
    coverage_pct DOUBLE PRECISION,
    checks       JSONB NOT NULL DEFAULT '{}',
    by_module    JSONB NOT NULL DEFAULT '{}',
    failures     JSONB NOT NULL DEFAULT '[]'
);

COMMIT;
