#!/usr/bin/env bash
# End-to-end smoke test (plan section 8.5): starts everything with Docker Compose, ingests
# examples/knowledge, asks a question with flock-ask and checks that a final reply with
# citations arrives.
#
# Uses the real LLM configured in .env (OPENROUTER_API_KEY, LLM_MODEL): run it only when closing
# a stage (D41). `LLM_PROVIDER=fake scripts/smoke.sh` checks the mechanics without the API key.
# The stack is left running.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

readonly IMAGE="flock-ai/agent-service:dev"
readonly NETWORK="flock-ai_default"
readonly PERSONA="juan-plataforma"
readonly QUESTION="¿Cómo hago rollback de un deploy?"
readonly EXPECTED_SOURCE="procedimientos/rollback.md"
repo_dir=$( (pwd -W 2>/dev/null) || pwd)
readonly REPO_DIR=$repo_dir

step() {
  printf '\n==> %s\n' "$1"
}

step "Starting the stack (docker compose up)"
docker compose up -d --wait --build

step "Ingesting examples/knowledge"
KNOWLEDGE_HOST_DIR=../examples/knowledge docker compose run --rm ingestion flock-ingest run

step "Asking $PERSONA: $QUESTION"
# flock-ask from a container on the Compose network, as the client app "cli".
set +e
output=$(MSYS_NO_PATHCONV=1 docker run --rm --network "$NETWORK" \
  --volume "$REPO_DIR/infra/certs/out/cli:/certs:ro" \
  --env KAFKA_BOOTSTRAP_SERVERS=kafka:9094 \
  --env TLS_CERT_FILE=/run/flock/certs/cli.crt \
  --env TLS_KEY_FILE=/run/flock/certs/cli.key \
  --env TLS_CA_FILE=/run/flock/certs/ca.crt \
  --env LOG_LEVEL=WARNING \
  "$IMAGE" flock-ask --persona "$PERSONA" "$QUESTION" 2>&1)
status=$?
set -e
printf '%s\n' "$output"

step "Checking the reply"
failures=0
check() {
  local description=$1 condition=$2
  if [ "$condition" = "yes" ]; then
    printf '  ok    %s\n' "$description"
  else
    printf '  FAIL  %s\n' "$description"
    failures=$((failures + 1))
  fi
}
contains() {
  case "$output" in *"$1"*) echo yes ;; *) echo no ;; esac
}
check "flock-ask finished with a final reply (exit code 0, got $status)" \
  "$([ "$status" -eq 0 ] && echo yes || echo no)"
check "the answer has sources" "$(contains "Sources:")"
check "it cites $EXPECTED_SOURCE" "$(contains "$EXPECTED_SOURCE")"
check "the outcome is answered" "$(contains "[answered")"

if [ "$failures" -gt 0 ]; then
  printf '\nSmoke test FAILED (%d checks)\n' "$failures"
  exit 1
fi
printf '\nSmoke test passed\n'
