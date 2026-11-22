-- =====================================================================
-- Control Center platform: initial PostgreSQL schema
-- Multi-tenant: every business-owned table carries business_id.
-- Requires PostgreSQL 13+ (gen_random_uuid is built in).
-- Run with: psql -d your_database -f schema.sql
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- Shared helper: keep updated_at current on every UPDATE
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- businesses: registered businesses using the platform
-- ---------------------------------------------------------------------
CREATE TABLE businesses (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,            -- URL-safe identifier
    industry    TEXT,
    country     TEXT,
    timezone    TEXT NOT NULL DEFAULT 'UTC',
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'suspended', 'closed')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- roles: Administrator, Manager, Employee, etc. (defined per business)
-- permissions is a JSON list/object so access rules can evolve
-- without a schema change.
-- ---------------------------------------------------------------------
CREATE TABLE roles (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id  UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    description  TEXT,
    permissions  JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (business_id, name)
);

-- ---------------------------------------------------------------------
-- users: people who log into the Control Center
-- ---------------------------------------------------------------------
CREATE TABLE users (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id    UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    role_id        UUID NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    email          TEXT NOT NULL,
    password_hash  TEXT NOT NULL,                -- store a hash (argon2/bcrypt), never the password
    full_name      TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active', 'invited', 'disabled')),
    last_login_at  TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Case-insensitive unique email across the platform
CREATE UNIQUE INDEX users_email_unique ON users (lower(email));
CREATE INDEX users_business_idx ON users (business_id);
CREATE INDEX users_role_idx ON users (role_id);

-- ---------------------------------------------------------------------
-- departments: Technical, Finance, Delivery, Customer Service, etc.
-- ---------------------------------------------------------------------
CREATE TABLE departments (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id  UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    description  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (business_id, name)
);

-- ---------------------------------------------------------------------
-- employees: staff members and their department assignments
-- user_id is optional: an employee may not have a login.
-- ---------------------------------------------------------------------
CREATE TABLE employees (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id    UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    user_id        UUID UNIQUE REFERENCES users(id) ON DELETE SET NULL,
    department_id  UUID REFERENCES departments(id) ON DELETE SET NULL,
    full_name      TEXT NOT NULL,
    email          TEXT,
    phone          TEXT,
    job_title      TEXT,
    status         TEXT NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active', 'on_leave', 'inactive')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX employees_business_idx ON employees (business_id);
CREATE INDEX employees_department_idx ON employees (department_id);

-- ---------------------------------------------------------------------
-- agents: AI assistants belonging to each business
-- config holds model, instructions, tools, and tuning settings.
-- ---------------------------------------------------------------------
CREATE TABLE agents (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id    UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    department_id  UUID REFERENCES departments(id) ON DELETE SET NULL,
    name           TEXT NOT NULL,
    description    TEXT,
    status         TEXT NOT NULL DEFAULT 'draft'
                   CHECK (status IN ('draft', 'active', 'paused', 'retired')),
    config         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (business_id, name)
);
CREATE INDEX agents_department_idx ON agents (department_id);

-- ---------------------------------------------------------------------
-- customers: a business's own customers
-- ---------------------------------------------------------------------
CREATE TABLE customers (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id  UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    full_name    TEXT NOT NULL,
    email        TEXT,
    phone        TEXT,
    external_ref TEXT,                           -- the business's own customer ID, if any
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX customers_business_idx ON customers (business_id);
CREATE INDEX customers_email_idx ON customers (business_id, lower(email));
CREATE INDEX customers_phone_idx ON customers (business_id, phone);

-- ---------------------------------------------------------------------
-- conversations: customer communication sessions
-- Handled by an AI agent, a human employee, or both over time.
-- ---------------------------------------------------------------------
CREATE TABLE conversations (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id  UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    customer_id  UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    agent_id     UUID REFERENCES agents(id) ON DELETE SET NULL,
    employee_id  UUID REFERENCES employees(id) ON DELETE SET NULL,
    channel      TEXT NOT NULL
                 CHECK (channel IN ('whatsapp', 'sms', 'email', 'phone', 'web_chat', 'other')),
    status       TEXT NOT NULL DEFAULT 'open'
                 CHECK (status IN ('open', 'waiting', 'closed')),
    summary      TEXT,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at     TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX conversations_business_status_idx ON conversations (business_id, status);
CREATE INDEX conversations_customer_idx ON conversations (customer_id);
CREATE INDEX conversations_agent_idx ON conversations (agent_id);

-- ---------------------------------------------------------------------
-- cases: customer problems requiring resolution
-- ---------------------------------------------------------------------
CREATE TABLE cases (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id           UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    customer_id           UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    conversation_id       UUID REFERENCES conversations(id) ON DELETE SET NULL,
    department_id         UUID REFERENCES departments(id) ON DELETE SET NULL,
    assigned_employee_id  UUID REFERENCES employees(id) ON DELETE SET NULL,
    assigned_agent_id     UUID REFERENCES agents(id) ON DELETE SET NULL,
    title                 TEXT NOT NULL,
    description           TEXT,
    priority              TEXT NOT NULL DEFAULT 'medium'
                          CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    status                TEXT NOT NULL DEFAULT 'open'
                          CHECK (status IN ('open', 'in_progress', 'waiting_customer', 'resolved', 'closed')),
    resolution_notes      TEXT,
    opened_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at           TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX cases_business_status_idx ON cases (business_id, status);
CREATE INDEX cases_customer_idx ON cases (customer_id);
CREATE INDEX cases_department_idx ON cases (department_id);
CREATE INDEX cases_employee_idx ON cases (assigned_employee_id);

-- ---------------------------------------------------------------------
-- updated_at triggers
-- ---------------------------------------------------------------------
DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'businesses', 'roles', 'users', 'departments', 'employees',
        'agents', 'customers', 'conversations', 'cases'
    ]
    LOOP
        EXECUTE format(
            'CREATE TRIGGER %I BEFORE UPDATE ON %I
             FOR EACH ROW EXECUTE FUNCTION set_updated_at()',
            t || '_set_updated_at', t
        );
    END LOOP;
END $$;

COMMIT;
