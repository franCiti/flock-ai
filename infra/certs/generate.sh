#!/bin/sh
# Development CA and service certificates for mTLS (plan section 7.1, D17).
#
# Usage:
#   infra/certs/generate.sh               create the CA and every service certificate
#   infra/certs/generate.sh client <id>   create a client certificate (see add-client.sh)
#
# On the host the script re-runs itself inside an OpenSSL container, so nothing has to be
# installed on Windows. The certs-init container of Docker Compose runs it directly.
# Existing files are never overwritten: delete infra/certs/out/ to start over.
set -eu

readonly OPENSSL_IMAGE="alpine/openssl:3.5.9"

if [ "${FLOCK_CERTS_IN_CONTAINER:-}" != "1" ]; then
  script_dir=$(cd "$(dirname "$0")" && pwd)
  # Git Bash: Docker Desktop needs a Windows path and no MSYS path conversion.
  host_dir=$(cd "$script_dir" && (pwd -W 2>/dev/null || pwd))
  user_args=""
  if [ "$(uname -s)" = "Linux" ] || [ "$(uname -s)" = "Darwin" ]; then
    user_args="--user $(id -u):$(id -g)"
  fi
  # shellcheck disable=SC2086 # user_args is intentionally split into words
  MSYS_NO_PATHCONV=1 exec docker run --rm $user_args \
    --env FLOCK_CERTS_IN_CONTAINER=1 \
    --volume "$host_dir:/certs" \
    --workdir /certs \
    --entrypoint sh \
    "$OPENSSL_IMAGE" /certs/generate.sh "$@"
fi

# --- Inside the container -------------------------------------------------------------------

readonly OUT_DIR="/certs/out"
readonly CA_DIR="$OUT_DIR/ca"
readonly CA_DAYS=3650
readonly SERVICE_DAYS=730

readonly SERVER_CERTS="kafka postgres"
readonly CLIENT_CERTS="core-api agent ingestion cli kafka-admin"

log() {
  printf '%s\n' "$*"
}

new_key() {
  openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$1"
  chmod 600 "$1"
}

create_ca() {
  if [ -f "$CA_DIR/ca.crt" ]; then
    log "ca: exists, kept"
    return
  fi
  mkdir -p "$CA_DIR"
  new_key "$CA_DIR/ca.key"
  openssl req -x509 -new -key "$CA_DIR/ca.key" -sha256 -days "$CA_DAYS" \
    -subj "/O=flock-ai/CN=flock-ai development CA" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -addext "subjectKeyIdentifier=hash" \
    -out "$CA_DIR/ca.crt"
  log "ca: created"
}

# issue <name> <server|client>
issue() {
  name=$1
  kind=$2
  dir="$OUT_DIR/$name"
  if [ -f "$dir/$name.crt" ]; then
    log "$name: exists, kept"
    return
  fi
  mkdir -p "$dir"
  extensions="$dir/extensions.cnf"
  {
    echo "basicConstraints=critical,CA:FALSE"
    echo "keyUsage=critical,digitalSignature"
    echo "authorityKeyIdentifier=keyid"
    echo "subjectKeyIdentifier=hash"
    if [ "$kind" = "server" ]; then
      # Brokers and databases also connect to themselves (health checks, admin tools).
      echo "extendedKeyUsage=serverAuth,clientAuth"
      echo "subjectAltName=DNS:$name,DNS:localhost,IP:127.0.0.1"
    else
      echo "extendedKeyUsage=clientAuth"
    fi
  } >"$extensions"

  new_key "$dir/$name.key"
  openssl req -new -key "$dir/$name.key" -subj "/O=flock-ai/CN=$name" -out "$dir/$name.csr"
  openssl x509 -req -in "$dir/$name.csr" -sha256 -days "$SERVICE_DAYS" \
    -CA "$CA_DIR/ca.crt" -CAkey "$CA_DIR/ca.key" -CAcreateserial \
    -extfile "$extensions" -out "$dir/$name.crt" 2>/dev/null
  rm -f "$dir/$name.csr" "$extensions"
  # Each container mounts only its own folder, so it gets its own copy of the CA certificate.
  cp "$CA_DIR/ca.crt" "$dir/ca.crt"
  log "$name: created ($kind)"
}

verify() {
  name=$1
  openssl verify -CAfile "$CA_DIR/ca.crt" "$OUT_DIR/$name/$name.crt" >/dev/null
  log "$name: verified"
}

validate_client_id() {
  case $1 in
    "" | *[!a-z0-9-]* | -*)
      log "invalid client id '$1': use lowercase letters, digits and '-'" >&2
      exit 2
      ;;
  esac
  if [ "${#1}" -gt 64 ]; then
    log "invalid client id '$1': at most 64 characters" >&2
    exit 2
  fi
}

case "${1:-all}" in
  all)
    create_ca
    for name in $SERVER_CERTS; do issue "$name" server; done
    for name in $CLIENT_CERTS; do issue "$name" client; done
    for name in $SERVER_CERTS $CLIENT_CERTS; do verify "$name"; done
    ;;
  client)
    client_id=${2:-}
    validate_client_id "$client_id"
    if [ ! -f "$CA_DIR/ca.crt" ]; then
      log "no CA found: run infra/certs/generate.sh first" >&2
      exit 1
    fi
    issue "$client_id" client
    verify "$client_id"
    ;;
  *)
    log "usage: generate.sh [all | client <id>]" >&2
    exit 2
    ;;
esac
