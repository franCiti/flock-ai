#!/usr/bin/env bash
# Creates the topics and ACLs (plan section 7.2, D25). Run by the kafka-init container.
#
# Usage:
#   setup.sh                every topic and ACL of the plan (idempotent)
#   setup.sh client <id>    reply topic and ACLs for a new client app of the agent
set -euo pipefail

# shellcheck source=infra/kafka/tls.sh
. /etc/flock/kafka/tls.sh

readonly BOOTSTRAP=kafka:9094
readonly ADMIN_CONFIG=/tmp/flock/admin.properties
readonly ONE_DAY_MS=86400000
readonly SEVEN_DAYS_MS=604800000

mkdir -p /tmp/flock
(umask 077 && client_properties /certs kafka-admin >"$ADMIN_CONFIG")

# create_topic <name> <partitions> <retention-ms>
create_topic() {
  /opt/kafka/bin/kafka-topics.sh --bootstrap-server "$BOOTSTRAP" --command-config "$ADMIN_CONFIG" \
    --create --if-not-exists --topic "$1" --partitions "$2" --replication-factor 1 \
    --config "retention.ms=$3"
}

# allow <user> <operation> <resource-type> <resource> [prefixed]
allow() {
  local pattern=literal
  if [[ ${5:-} == prefixed ]]; then
    pattern=prefixed
  fi
  /opt/kafka/bin/kafka-acls.sh --bootstrap-server "$BOOTSTRAP" --command-config "$ADMIN_CONFIG" \
    --add --allow-principal "User:$1" --operation "$2" "--$3" "$4" \
    --resource-pattern-type "$pattern" >/dev/null
  echo "ACL: $1 $2 $3 $4 ($pattern)"
}

# setup_client <id>: a client app publishes questions and reads its own replies.
setup_client() {
  local id=$1
  create_topic "agent.replies.$id" 3 "$ONE_DAY_MS"
  allow "$id" Write topic agent.requests
  allow "$id" Read topic "agent.replies.$id"
  allow "$id" Read group "$id"
}

setup_all() {
  create_topic agent.requests 6 "$ONE_DAY_MS"
  create_topic agent.audit 3 "$SEVEN_DAYS_MS"
  create_topic ingestion.jobs 1 "$SEVEN_DAYS_MS"
  create_topic ingestion.events 1 "$SEVEN_DAYS_MS"

  # Client apps of the agent.
  setup_client core-api
  setup_client cli

  # core-api is also the owner of the ingestion and the reader of the audit log.
  allow core-api Write topic ingestion.jobs
  allow core-api Read topic ingestion.events
  allow core-api Read topic agent.audit

  # Agent Worker.
  allow agent Read topic agent.requests
  allow agent Write topic agent.replies. prefixed
  allow agent Write topic agent.audit
  allow agent Read group agent

  # Ingestion Worker.
  allow ingestion Read topic ingestion.jobs
  allow ingestion Write topic ingestion.events
  allow ingestion Read group ingestion
}

case "${1:-all}" in
  all) setup_all ;;
  client)
    if [[ ! ${2:-} =~ ^[a-z0-9][a-z0-9-]{0,63}$ ]]; then
      echo "usage: setup.sh client <id> (lowercase letters, digits and '-')" >&2
      exit 2
    fi
    setup_client "$2"
    ;;
  *)
    echo "usage: setup.sh [all | client <id>]" >&2
    exit 2
    ;;
esac
echo "Kafka setup done"
