#!/bin/sh
# Registers a new client app of the agent (plan section 7.1, D25).
#
# Usage: infra/certs/add-client.sh <clientId>
#
# Creates the client certificate (CN=<clientId>). The client then publishes to agent.requests
# with replyTo = agent.replies.<clientId>.
# TODO(T07): also create the agent.replies.<clientId> topic and its Kafka ACLs.
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: add-client.sh <clientId>" >&2
  exit 2
fi

exec "$(dirname "$0")/generate.sh" client "$1"
