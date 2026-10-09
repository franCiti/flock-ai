#!/usr/bin/env bash
# Validates asyncapi.yaml and generates its HTML documentation into contracts/docs/ (gitignored).
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# Pinned so every run produces the same documentation.
readonly ASYNCAPI_CLI="@asyncapi/cli@6.2.0"
readonly HTML_TEMPLATE="@asyncapi/html-template@3"

# No usage analytics from the AsyncAPI CLI.
export ASYNCAPI_METRICS=false
export SUPPRESS_NO_CONFIG_WARNING=1

npx --yes "$ASYNCAPI_CLI" validate asyncapi.yaml
npx --yes "$ASYNCAPI_CLI" generate fromTemplate asyncapi.yaml "$HTML_TEMPLATE" \
  --output docs --force-write

echo "Documentation generated in contracts/docs/index.html"
