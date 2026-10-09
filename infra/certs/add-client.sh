#!/bin/sh
# Registers a new client app of the agent (plan section 7.1, D25).
#
# Usage: infra/certs/add-client.sh <clientId>     (Kafka must be running: docker compose up -d)
#
# 1. Creates the client certificate (CN=<clientId>).
# 2. Creates its reply topic agent.replies.<clientId> and its Kafka ACLs: write agent.requests,
#    read its reply topic and its consumer group <clientId>.
# The client then publishes to agent.requests with replyTo = agent.replies.<clientId>.
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: add-client.sh <clientId>" >&2
  exit 2
fi

repo_root=$(cd "$(dirname "$0")/../.." && pwd)

"$repo_root/infra/certs/generate.sh" client "$1"
cd "$repo_root"
docker compose run --rm kafka-init client "$1"
