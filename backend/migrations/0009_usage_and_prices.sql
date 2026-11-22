-- Per-call usage with cost ESTIMATES (tenant-scoped) and platform-wide price records.
-- Apply after 0008:  psql -d your_database -f migrations/0009_usage_and_prices.sql
BEGIN;

CREATE TABLE usage_sessions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id      UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    session_id       UUID NOT NULL,
    conversation_id  UUID REFERENCES conversations(id) ON DELETE SET NULL,
    source           TEXT NOT NULL DEFAULT 'test_call',
    started_at       TIMESTAMPTZ NOT NULL,
    ended_at         TIMESTAMPTZ NOT NULL,
    stt_seconds      INTEGER NOT NULL DEFAULT 0,
    tts_characters   INTEGER NOT NULL DEFAULT 0,
    llm_requests     INTEGER NOT NULL DEFAULT 0,
    llm_usage        JSONB NOT NULL DEFAULT '[]',
    failed_requests  INTEGER NOT NULL DEFAULT 0,
    retries          INTEGER NOT NULL DEFAULT 0,
    turns            INTEGER NOT NULL DEFAULT 0,
    latency_avg_ms   INTEGER,
    latency_max_ms   INTEGER,
    cost_micro_usd   BIGINT NOT NULL DEFAULT 0,
    cost_complete    BOOLEAN NOT NULL DEFAULT FALSE,
    missing_rates    JSONB NOT NULL DEFAULT '[]',
    pricing_snapshot JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX usage_sessions_business_time_idx ON usage_sessions (business_id, ended_at);

CREATE TABLE price_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item            TEXT NOT NULL,
    rate            TEXT NOT NULL,
    effective_from  DATE NOT NULL,
    source_note     TEXT NOT NULL DEFAULT '',
    created_by      UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX price_records_item_idx ON price_records (item, effective_from);

COMMIT;
