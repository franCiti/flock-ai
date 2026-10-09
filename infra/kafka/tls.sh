#!/usr/bin/env bash
# Helpers to write Kafka TLS settings with the PEM material inline (sourced, not executed).
#
# Kafka only accepts an unencrypted PEM key as an inline config value, written as a properties
# value continued over several lines.

# pem_property <property> <pem-file>
pem_property() {
  printf '%s=' "$1"
  # Every line ends with " \" (continuation) except the last one.
  sed -e 's/$/ \\/' "$2" | sed -e '$ s/ \\$//'
}

# client_properties <certificate-dir> <name>
# Prints the configuration of a Kafka client authenticated with <dir>/<name>.crt and .key.
client_properties() {
  local dir=$1 name=$2
  echo "security.protocol=SSL"
  echo "ssl.protocol=TLSv1.3"
  echo "ssl.enabled.protocols=TLSv1.3"
  echo "ssl.keystore.type=PEM"
  echo "ssl.truststore.type=PEM"
  pem_property ssl.keystore.certificate.chain "$dir/$name.crt"
  pem_property ssl.keystore.key "$dir/$name.key"
  pem_property ssl.truststore.certificates "$dir/ca.crt"
}
