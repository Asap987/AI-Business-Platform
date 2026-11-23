-- Departmental routing: opening hours, extensions, availability, fallback departments, callback requests.
-- Apply after 0010:  psql -d your_database -f migrations/0011_routing.sql
BEGIN;

-- hours: NULL = always open. Otherwise {"mon": [["08:00","17:00"]], ...}; a day that is missing is closed.
ALTER TABLE departments
    ADD COLUMN hours                  JSONB,
    ADD COLUMN timezone               TEXT,
    ADD COLUMN fallback_department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    ADD COLUMN accepts_transfers      BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE employees
    ADD COLUMN extension        TEXT,
    ADD COLUMN available        BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN routing_priority INTEGER NOT NULL DEFAULT 100;

CREATE TABLE callback_requests (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id    UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    department_id  UUID REFERENCES departments(id) ON DELETE SET NULL,
    customer_id    UUID REFERENCES customers(id) ON DELETE SET NULL,
    caller_name    TEXT,
    phone          TEXT NOT NULL,
    reason         TEXT NOT NULL,
    preferred_time TEXT,
    context        JSONB NOT NULL DEFAULT '{}'::jsonb,   -- what the assistant already learned, so nobody asks again
    source         TEXT NOT NULL DEFAULT 'ai' CHECK (source IN ('ai', 'staff')),
    status         TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'contacted', 'done', 'cancelled')),
    note           TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX callback_requests_business_status_idx ON callback_requests (business_id, status, created_at);
CREATE TRIGGER callback_requests_set_updated_at BEFORE UPDATE ON callback_requests
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;
