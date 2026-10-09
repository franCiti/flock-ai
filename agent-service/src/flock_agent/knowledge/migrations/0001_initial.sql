-- Knowledge base (plan section 3.2). Applied by the ingestion role, owner of the schema.
-- The agent role can read every table (default privileges, infra/postgres/initdb).

-- yoyo runs migrations with search_path = knowledge only; pgvector's types live in public.
SET LOCAL search_path = knowledge, public;

-- One persona per knowledge folder (spec HU9).
CREATE TABLE persona (
    id            text PRIMARY KEY CHECK (id ~ '^[a-z0-9][a-z0-9-]{0,62}$'),
    display_name  text NOT NULL CHECK (display_name <> ''),
    identities    jsonb NOT NULL DEFAULT '{}',
    profile_hash  text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

-- Every file, email, attachment, issue or page.
CREATE TABLE document (
    id                 text PRIMARY KEY,
    persona_id         text NOT NULL REFERENCES persona (id) ON DELETE CASCADE,
    source_type        text NOT NULL CHECK (source_type IN (
                           'file', 'email', 'email_attachment', 'jira', 'confluence', 'sharepoint')),
    source_id          text,            -- external source; NULL = the persona folder
    parent_id          text,            -- email attachment -> its email
    title              text NOT NULL,
    url                text,
    path               text,
    section_hint       text,
    source_updated_at  timestamptz NOT NULL,
    content_hash       text NOT NULL,
    secrets_masked     integer NOT NULL DEFAULT 0 CHECK (secrets_masked >= 0),
    indexed_at         timestamptz NOT NULL DEFAULT now(),
    -- Lets chunk reference (id, persona_id) and guarantees both belong to the same persona.
    UNIQUE (id, persona_id),
    FOREIGN KEY (parent_id, persona_id) REFERENCES document (id, persona_id) ON DELETE CASCADE
);
CREATE INDEX document_persona_source_idx ON document (persona_id, source_id);

-- The fragments that are searched. persona_id is repeated on purpose: every search filters by
-- persona without a join (spec HU3), and the foreign key keeps it consistent with the document.
CREATE TABLE chunk (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id   text NOT NULL,
    persona_id    text NOT NULL,
    ordinal       integer NOT NULL CHECK (ordinal >= 0),
    heading_path  text NOT NULL DEFAULT '',
    content       text NOT NULL,
    -- Dimensions of the current embedding model (plan 5.5); a model change rebuilds this column.
    embedding     vector(384) NOT NULL,
    -- Exact-word search (job names, error codes, acronyms). 'simple': no language stemming,
    -- because the knowledge base mixes languages.
    tsv           tsvector GENERATED ALWAYS AS (
                      to_tsvector('simple', heading_path || ' ' || content)) STORED,
    UNIQUE (document_id, ordinal),
    FOREIGN KEY (document_id, persona_id) REFERENCES document (id, persona_id) ON DELETE CASCADE
);
CREATE INDEX chunk_persona_idx ON chunk (persona_id);
CREATE INDEX chunk_embedding_idx ON chunk USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunk_tsv_idx ON chunk USING gin (tsv);

-- Where each incremental sync stopped (plan 5.1).
CREATE TABLE sync_state (
    persona_id      text NOT NULL REFERENCES persona (id) ON DELETE CASCADE,
    source_key      text NOT NULL,      -- 'folder' or the external source id
    cursor          jsonb NOT NULL,
    last_synced_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (persona_id, source_key)
);

-- History of knowledge updates (spec HU4.5).
CREATE TABLE ingestion_run (
    job_id       uuid PRIMARY KEY,
    trigger      text NOT NULL CHECK (trigger IN ('scheduled', 'manual')),
    status       text NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'rejected')),
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    summary      jsonb
);

-- Key/value settings of the knowledge base (e.g. the embedding model it was indexed with).
CREATE TABLE meta (
    key    text PRIMARY KEY,
    value  text NOT NULL
);
