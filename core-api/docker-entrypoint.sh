#!/bin/sh
# Entry point of the core-api image (plan section 7.5).
#
# certs-init writes the private keys with mode 600, owned by root. Running as root only for that,
# this script copies the TLS material mounted in /certs to a private folder of the "flock" user and
# then runs the command as "flock". TLS_CERT_FILE, TLS_KEY_FILE and TLS_CA_FILE point to the copies
# (/run/flock/certs/<file>).
set -eu

readonly SERVICE_USER=flock
readonly CERTS_IN=/certs
readonly CERTS_OUT=/run/flock/certs

if [ "$(id -u)" != "0" ]; then
  exec "$@"
fi

install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 700 /run/flock "$CERTS_OUT"
if [ -d "$CERTS_IN" ]; then
  for file in "$CERTS_IN"/*; do
    [ -f "$file" ] && install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 600 "$file" "$CERTS_OUT/"
  done
fi

# setpriv keeps the environment: HOME must be a folder "flock" can use.
export HOME=/run/flock
exec setpriv --reuid="$SERVICE_USER" --regid="$SERVICE_USER" --init-groups -- "$@"
