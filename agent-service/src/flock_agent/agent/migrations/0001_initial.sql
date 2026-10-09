-- Conversations, idempotency, rate limits and audit (plan section 3.3). Applied by the agent
-- role, owner of the schema. LangGraph's checkpoint tables are created by its own library.
-- Persona ids are not foreign keys: knowledge belongs to another role, and the audit log must
-- survive a persona that is removed.

-- Retention of each conversation (spec HU5.3). Two client apps can use the same
-- conversation id without mixing: the key includes the client.
CREATE TABLE conversation (
    client_id        text NOT NULL,
    conversation_id  text NOT NULL,
    persona_id       text NOT NULL,
    -- Goes up when the conversation expires or changes persona: a new LangGraph thread.
    generation       integer NOT NULL DEFAULT 0 CHECK (generation >= 0),
    last_message_at  timestamptz NOT NULL,
    PRIMARY KEY (client_id, conversation_id)
);
CREATE INDEX conversation_last_message_idx ON conversation (last_message_at);

-- Requests already answered: a repeated request id is not processed twice (spec, edge cases).
CREATE TABLE processed_request (
    request_id   uuid PRIMARY KEY,
    client_id    text NOT NULL,
    received_at  timestamptz NOT NULL
);
CREATE INDEX processed_request_received_idx ON processed_request (received_at);

-- Requests per minute per client app (spec HU15.5). In the database, not in memory, so the
-- limit holds with several Agent Workers.
CREATE TABLE rate_limit_window (
    client_id      text NOT NULL,
    window_start   timestamptz NOT NULL,
    request_count  integer NOT NULL CHECK (request_count > 0),
    PRIMARY KEY (client_id, window_start)
);
CREATE INDEX rate_limit_window_start_idx ON rate_limit_window (window_start);

-- What was answered (spec HU8, HU15.7). Same content as the AuditEntry message of agent.audit.
-- Identifiers are NULL for requests that could not be read.
CREATE TABLE audit_entry (
    id                   uuid PRIMARY KEY,
    request_id           uuid,
    client_id            text,
    conversation_id      text,
    persona_id           text,
    question             text,
    answer               text,
    outcome              text NOT NULL CHECK (outcome IN (
                             'answered', 'partially_answered', 'no_information', 'out_of_scope',
                             'small_talk', 'about_assistant', 'error')),
    error_code           text CHECK (error_code IN (
                             'INVALID_REQUEST', 'UNSUPPORTED_VERSION', 'PERSONA_NOT_FOUND',
                             'QUESTION_TOO_LONG', 'RATE_LIMITED', 'TIMEOUT', 'LLM_UNAVAILABLE',
                             'INTERNAL_ERROR')),
    citations            jsonb NOT NULL DEFAULT '[]',
    referral_persona_id  text,
    flags                text[] NOT NULL DEFAULT '{}' CHECK (flags <@ ARRAY[
                             'injection_suspected', 'rate_limited', 'question_too_long',
                             'invalid_request']::text[]),
    llm_model            text,
    prompt_version       text,
    first_token_ms       integer CHECK (first_token_ms >= 0),
    total_ms             integer CHECK (total_ms >= 0),
    created_at           timestamptz NOT NULL
);
-- Filters of the web interface (spec HU8.2).
CREATE INDEX audit_entry_persona_created_idx ON audit_entry (persona_id, created_at);
CREATE INDEX audit_entry_created_idx ON audit_entry (created_at);
CREATE INDEX audit_entry_flags_idx ON audit_entry USING gin (flags);
