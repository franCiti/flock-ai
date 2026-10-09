#!/bin/sh
# Starts PostgreSQL with TLS and certificate authentication (plan section 7.3, D17).
#
# PostgreSQL refuses a private key readable by other users, and bind mounts from Windows show
# every file as world-readable. So the TLS material is copied with the right owner and mode
# before handing over to the official entrypoint.
set -eu

readonly TLS_DIR=/var/lib/postgresql/tls

install -d -o postgres -g postgres -m 700 "$TLS_DIR"
install -o postgres -g postgres -m 600 /certs/postgres.key "$TLS_DIR/server.key"
install -o postgres -g postgres -m 644 /certs/postgres.crt "$TLS_DIR/server.crt"
install -o postgres -g postgres -m 644 /certs/ca.crt "$TLS_DIR/ca.crt"

exec docker-entrypoint.sh postgres \
  -c listen_addresses='*' \
  -c ssl=on \
  -c ssl_min_protocol_version=TLSv1.3 \
  -c ssl_cert_file="$TLS_DIR/server.crt" \
  -c ssl_key_file="$TLS_DIR/server.key" \
  -c ssl_ca_file="$TLS_DIR/ca.crt" \
  -c hba_file=/etc/flock/pg_hba.conf \
  -c ident_file=/etc/flock/pg_ident.conf
