-- Approved business information the AI assistant may quote (hours, policies, procedures).
-- Apply after 0004:  psql -d your_database -f migrations/0005_knowledge_base.sql
BEGIN;

CREATE TABLE knowledge_documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    category    TEXT,
    content     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'published' CHECK (status IN ('published', 'archived')),
    created_by  UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX knowledge_documents_business_idx ON knowledge_documents (business_id, status);

-- Search works on small pieces of each document, so only the relevant pieces reach the AI provider.
CREATE TABLE knowledge_chunks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    text        TEXT NOT NULL
);
CREATE INDEX knowledge_chunks_business_idx ON knowledge_chunks (business_id);
CREATE INDEX knowledge_chunks_document_idx ON knowledge_chunks (document_id, position);

COMMIT;
