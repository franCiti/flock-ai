-- Users of the web app (spec HU10.1, D16, plan 3.4). Passwords only as BCrypt hashes.
CREATE TABLE app_user (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username       text NOT NULL UNIQUE CHECK (username <> ''),
    password_hash  text NOT NULL,
    enabled        boolean NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now()
);
