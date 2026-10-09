#!/usr/bin/env bash
# Verifies PostgreSQL authentication and privileges (task T06, plan sections 3.1 and 7.3).
# Requires the stack running: docker compose up -d postgres
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."

readonly IMAGE="pgvector/pgvector:0.8.7-pg17"
readonly NETWORK="flock-ai_default"
certs_dir=$( (cd infra/certs/out && pwd -W 2>/dev/null) || (cd infra/certs/out && pwd))
readonly CERTS_DIR=$certs_dir

failures=0

# psql_as <certificate> <role> <sql> [sslmode]
# Runs one statement from a throwaway container on the Compose network, authenticated with the
# given client certificate ("none" = no certificate).
psql_as() {
  local cert=$1 role=$2 sql=$3 sslmode=${4:-verify-full}
  local conninfo="host=postgres dbname=flock_ai user=$role sslmode=$sslmode sslrootcert=/certs/ca/ca.crt"
  if [[ $cert != none ]]; then
    conninfo+=" sslcert=/tmp/client.crt sslkey=/tmp/client.key"
  fi
  # libpq refuses a world-readable key, so it is copied with mode 600 first.
  MSYS_NO_PATHCONV=1 docker run --rm --network "$NETWORK" \
    --volume "$CERTS_DIR:/certs:ro" --entrypoint sh "$IMAGE" -c "
      if [ '$cert' != none ]; then
        install -m 600 /certs/$cert/$cert.key /tmp/client.key
        cp /certs/$cert/$cert.crt /tmp/client.crt
      fi
      psql '$conninfo' --no-psqlrc --tuples-only --no-align --command \"$sql\"" 2>&1
}

expect_ok() {
  local description=$1 output
  shift
  if output=$(psql_as "$@"); then
    printf 'PASS  %s\n' "$description"
  else
    printf 'FAIL  %s\n      %s\n' "$description" "$output"
    failures=$((failures + 1))
  fi
}

expect_rejected() {
  local description=$1 pattern=$2 output
  shift 2
  if output=$(psql_as "$@"); then
    printf 'FAIL  %s (it was allowed)\n' "$description"
    failures=$((failures + 1))
  elif grep -qiE "$pattern" <<<"$output"; then
    printf 'PASS  %s\n' "$description"
  else
    printf 'FAIL  %s (unexpected error)\n      %s\n' "$description" "$output"
    failures=$((failures + 1))
  fi
}

echo "== Authentication"
expect_ok "core-api certificate logs in as core_api" core-api core_api "SELECT current_user"
expect_ok "agent certificate logs in as agent" agent agent "SELECT current_user"
expect_ok "ingestion certificate logs in as ingestion" ingestion ingestion "SELECT current_user"
expect_rejected "no client certificate" "certificate|authentication failed" none agent "SELECT 1"
expect_rejected "TLS disabled" "no pg_hba.conf entry|SSL off" none agent "SELECT 1" disable
expect_rejected "agent certificate claiming the ingestion role" "authentication failed" \
  agent ingestion "SELECT 1"
expect_rejected "certificate without a mapped role (cli)" "authentication failed" cli agent "SELECT 1"
expect_rejected "superuser over the network" "authentication failed" agent postgres "SELECT 1"

echo "== Privileges"
expect_ok "ingestion creates and fills a table in knowledge" ingestion ingestion \
  "CREATE TABLE knowledge.t06_check (id int); INSERT INTO knowledge.t06_check VALUES (1)"
expect_ok "agent reads knowledge" agent agent "SELECT count(*) FROM knowledge.t06_check"
expect_rejected "agent cannot write knowledge" "permission denied" agent agent \
  "INSERT INTO knowledge.t06_check VALUES (2)"
expect_rejected "agent cannot create tables in knowledge" "permission denied" agent agent \
  "CREATE TABLE knowledge.t06_intruder (id int)"
expect_rejected "core_api cannot read knowledge" "permission denied" core-api core_api \
  "SELECT count(*) FROM knowledge.t06_check"
expect_rejected "ingestion cannot write the agent schema" "permission denied" ingestion ingestion \
  "CREATE TABLE agent.t06_intruder (id int)"
expect_rejected "nobody creates objects in public" "permission denied" core-api core_api \
  "CREATE TABLE public.t06_intruder (id int)"
expect_ok "every service can use pgvector" agent agent "SELECT '[1,2,3]'::vector <=> '[1,2,4]'::vector"
expect_ok "cleanup" ingestion ingestion "DROP TABLE knowledge.t06_check"

if ((failures > 0)); then
  echo "$failures check(s) failed"
  exit 1
fi
echo "All PostgreSQL checks passed"
