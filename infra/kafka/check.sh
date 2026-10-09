#!/usr/bin/env bash
# Verifies Kafka TLS, authentication and ACLs with real traffic (task T07, plan section 7.2).
# Requires the stack running: docker compose up -d --wait
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."

readonly IMAGE="apache/kafka:4.3.1"
readonly NETWORK="flock-ai_default"
readonly BOOTSTRAP="kafka:9094"
repo_dir=$( (pwd -W 2>/dev/null) || pwd)
readonly REPO_DIR=$repo_dir
readonly PROBE="t07-probe-$RANDOM"

failures=0

# kafka_client <certificate|none> <shell command using $CONFIG>
# Runs a Kafka CLI command from a throwaway container on the Compose network, authenticated with
# the given client certificate ("none" = TLS without a client certificate).
kafka_client() {
  local cert=$1 command=$2
  MSYS_NO_PATHCONV=1 docker run --rm --user 0 --network "$NETWORK" \
    --volume "$REPO_DIR/infra/kafka:/etc/flock/kafka:ro" \
    --volume "$REPO_DIR/infra/certs/out:/certs:ro" \
    --entrypoint bash "$IMAGE" -c "
      set -e
      . /etc/flock/kafka/tls.sh
      CONFIG=/tmp/client.properties
      if [ '$cert' = none ]; then
        printf 'security.protocol=SSL\nssl.truststore.type=PEM\n' >\$CONFIG
        pem_property ssl.truststore.certificates /certs/ca/ca.crt >>\$CONFIG
      else
        client_properties /certs/$cert $cert >\$CONFIG
      fi
      export KAFKA_OPTS=-Dlog4j2.level=WARN
      $command" 2>&1
}

produce() { # <cert> <topic>
  kafka_client "$1" "echo $PROBE | /opt/kafka/bin/kafka-console-producer.sh \
    --bootstrap-server $BOOTSTRAP --topic $2 --producer.config \$CONFIG \
    --command-property request.timeout.ms=10000 --command-property max.block.ms=10000"
}

consume() { # <cert> <topic> <group>
  kafka_client "$1" "/opt/kafka/bin/kafka-console-consumer.sh \
    --bootstrap-server $BOOTSTRAP --topic $2 --group $3 --from-beginning \
    --max-messages 1 --timeout-ms 15000 --consumer.config \$CONFIG"
}

report() { # <description> <passed: 0|1> <output>
  if [[ $2 == 1 ]]; then
    printf 'PASS  %s\n' "$1"
  else
    printf 'FAIL  %s\n%s\n' "$1" "$(tail -3 <<<"$3" | sed 's/^/      /')"
    failures=$((failures + 1))
  fi
}

expect_produce_ok() { # <description> <cert> <topic>
  local output
  output=$(produce "$2" "$3") || true
  if grep -qE "ERROR|Exception" <<<"$output"; then report "$1" 0 "$output"; else report "$1" 1 ""; fi
}

expect_produce_denied() { # <description> <cert> <topic>
  local output
  output=$(produce "$2" "$3") || true
  if grep -qE "TopicAuthorizationException|Not authorized" <<<"$output"; then
    report "$1" 1 ""
  else
    report "$1" 0 "$output"
  fi
}

expect_consume_probe() { # <description> <cert> <topic> <group>
  local output
  output=$(consume "$2" "$3" "$4") || true
  if grep -qx "$PROBE" <<<"$output"; then report "$1" 1 ""; else report "$1" 0 "$output"; fi
}

expect_consume_denied() { # <description> <cert> <topic> <group>
  local output
  output=$(consume "$2" "$3" "$4") || true
  if grep -qE "AuthorizationException|Not authorized" <<<"$output"; then
    report "$1" 1 ""
  else
    report "$1" 0 "$output"
  fi
}

echo "== Topics"
topics=$(kafka_client kafka-admin "/opt/kafka/bin/kafka-topics.sh --bootstrap-server $BOOTSTRAP \
  --command-config \$CONFIG --describe --exclude-internal" || true)
for expected in "agent.requests 6" "agent.replies.core-api 3" "agent.replies.cli 3" \
  "agent.audit 3" "ingestion.jobs 1" "ingestion.events 1"; do
  read -r topic partitions <<<"$expected"
  if grep -qE "^Topic: $topic\s.*PartitionCount: $partitions\s" <<<"$topics"; then
    report "$topic exists with $partitions partition(s)" 1 ""
  else
    report "$topic exists with $partitions partition(s)" 0 "$topics"
  fi
done

echo "== Authentication"
output=$(kafka_client none "timeout 30 /opt/kafka/bin/kafka-broker-api-versions.sh \
  --bootstrap-server $BOOTSTRAP --command-config \$CONFIG") || true
if grep -qiE "SslAuthenticationException|handshake" <<<"$output"; then
  report "a client without certificate is rejected" 1 ""
else
  report "a client without certificate is rejected" 0 "$output"
fi

# The EXTERNAL listener (localhost:9093) is the one clients on the PC use: check its mTLS
# handshake and that its certificate is valid for "localhost".
output=$(MSYS_NO_PATHCONV=1 docker run --rm --volume "$REPO_DIR/infra/certs/out/cli:/certs:ro" \
  --entrypoint sh alpine/openssl:3.5.9 -c "
    echo | openssl s_client -connect host.docker.internal:9093 -servername localhost \
      -verify_hostname localhost -verify_return_error -CAfile /certs/ca.crt \
      -cert /certs/cli.crt -key /certs/cli.key 2>&1" || true)
if grep -q "Verify return code: 0 (ok)" <<<"$output" && grep -q "TLSv1.3" <<<"$output"; then
  report "EXTERNAL listener: TLS 1.3, certificate valid for localhost" 1 ""
else
  report "EXTERNAL listener: TLS 1.3, certificate valid for localhost" 0 "$output"
fi

echo "== Request flow: core-api -> agent -> core-api"
expect_produce_ok "core-api publishes to agent.requests" core-api agent.requests
expect_consume_probe "agent reads agent.requests (group agent)" agent agent.requests agent
expect_produce_ok "agent publishes to agent.replies.core-api (prefix ACL)" agent agent.replies.core-api
expect_consume_probe "core-api reads its replies (group core-api)" core-api agent.replies.core-api core-api

echo "== Denied"
expect_consume_denied "cli cannot read the replies of core-api" cli agent.replies.core-api cli
expect_consume_denied "agent cannot use the group of core-api" agent agent.requests core-api
expect_produce_denied "ingestion cannot publish questions" ingestion agent.requests
expect_produce_denied "core-api cannot publish ingestion events" core-api ingestion.events
expect_produce_denied "cli cannot publish to the audit log" cli agent.audit
expect_produce_denied "agent cannot request ingestions" agent ingestion.jobs

if ((failures > 0)); then
  echo "$failures check(s) failed"
  exit 1
fi
echo "All Kafka checks passed"
