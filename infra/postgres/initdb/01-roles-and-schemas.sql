-- Roles, schemas and privileges (plan sections 3.1 and 7.3).
-- Runs once, when the data volume is created. Tables are created by each service's migrations.

CREATE EXTENSION IF NOT EXISTS vector;

-- One role per service. No passwords: they authenticate with their client certificate.
CREATE ROLE core_api LOGIN;
CREATE ROLE ingestion LOGIN;
CREATE ROLE agent LOGIN;

-- Nobody else can connect or create temporary tables.
REVOKE ALL ON DATABASE flock_ai FROM PUBLIC;
GRANT CONNECT ON DATABASE flock_ai TO core_api, ingestion, agent;

-- The public schema only holds the pgvector extension: usable, but nobody creates objects there.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO core_api, ingestion, agent;

-- Each service owns its schema (D12).
CREATE SCHEMA core AUTHORIZATION core_api;
CREATE SCHEMA knowledge AUTHORIZATION ingestion;
CREATE SCHEMA agent AUTHORIZATION agent;

-- The agent reads the knowledge base but can never modify it.
GRANT USAGE ON SCHEMA knowledge TO agent;
ALTER DEFAULT PRIVILEGES FOR ROLE ingestion IN SCHEMA knowledge GRANT SELECT ON TABLES TO agent;

ALTER ROLE core_api SET search_path = core, public;
ALTER ROLE ingestion SET search_path = knowledge, public;
ALTER ROLE agent SET search_path = agent, knowledge, public;
