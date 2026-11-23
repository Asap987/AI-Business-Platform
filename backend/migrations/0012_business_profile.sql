-- Organisation profile: description, contact details, branches, hours, policies, languages, customer-service preferences.
-- Apply after 0011:  psql -d your_database -f migrations/0012_business_profile.sql
BEGIN;

CREATE TABLE business_profiles (
    business_id   UUID PRIMARY KEY REFERENCES businesses(id) ON DELETE CASCADE,
    description   TEXT,
    contact_phone TEXT,
    contact_email TEXT,
    website       TEXT,
    address       TEXT,
    branches      JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{name, address, phone}]
    hours         JSONB,                                 -- same format as departments.hours; NULL = not stated
    policies      JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{title, text}]
    languages     JSONB NOT NULL DEFAULT '[]'::jsonb,   -- ["English", "Twi"]
    preferences   JSONB NOT NULL DEFAULT '{}'::jsonb,   -- {greeting, tone, after_hours_message, escalation_note}
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER business_profiles_set_updated_at BEFORE UPDATE ON business_profiles
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;
