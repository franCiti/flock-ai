-- Read copies of the data of the Python services, filled from Kafka (plan 3.4, 3.5). Java never
-- reads the schemas of Python: these tables are updated with idempotent upserts by id.

-- Personas available to the web app (spec HU10.2), from ingestion.events.
CREATE TABLE persona_view (
    id            text PRIMARY KEY,
    display_name  text NOT NULL,
    updated_at    timestamptz NOT NULL
);

-- Knowledge updates and their result (spec HU4.5), from ingestion.events.
CREATE TABLE ingestion_run_view (
    job_id            uuid PRIMARY KEY,
    -- Who asked for it; known when the Core API publishes the job (T35), NULL otherwise.
    trigger           text CHECK (trigger IN ('scheduled', 'manual')),
    status            text NOT NULL CHECK (status IN ('requested', 'running', 'completed', 'failed', 'rejected')),
    requested_at      timestamptz,
    started_at        timestamptz,
    finished_at       timestamptz,
    totals            jsonb,
    -- Summary of each updated persona, by persona id (the same summary twice is the same object).
    personas          jsonb NOT NULL DEFAULT '{}',
    removed_personas  jsonb NOT NULL DEFAULT '[]',
    reason            text,
    updated_at        timestamptz NOT NULL
);
CREATE INDEX ingestion_run_view_requested_idx ON ingestion_run_view (coalesce(requested_at, started_at) DESC);

-- What the agent answered (spec HU8), from agent.audit. Same content as the AuditEntry message.
CREATE TABLE audit_entry_view (
    id                   uuid PRIMARY KEY,
    request_id           uuid,
    client_id            text,
    conversation_id      text,
    persona_id           text,
    question             text,
    answer               text,
    outcome              text NOT NULL,
    error_code           text,
    citations            jsonb NOT NULL DEFAULT '[]',
    referral_persona_id  text,
    flags                text[] NOT NULL DEFAULT '{}',
    llm_model            text,
    prompt_version       text,
    first_token_ms       integer,
    total_ms             integer,
    created_at           timestamptz NOT NULL
);
-- Filters of the web interface (spec HU8.2): persona, dates, outcome and flags.
CREATE INDEX audit_entry_view_persona_created_idx ON audit_entry_view (persona_id, created_at DESC);
CREATE INDEX audit_entry_view_created_idx ON audit_entry_view (created_at DESC);
CREATE INDEX audit_entry_view_outcome_idx ON audit_entry_view (outcome);
CREATE INDEX audit_entry_view_flags_idx ON audit_entry_view USING gin (flags);
