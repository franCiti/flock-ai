#!/usr/bin/env bash
# Runs every linter and every test suite in the repository.
# Projects that do not exist yet are skipped.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

step() {
  printf '\n==> %s\n' "$1"
}

step "Linters (pre-commit)"
pre-commit run --all-files

if [[ -f agent-service/pyproject.toml ]]; then
  step "agent-service tests"
  (cd agent-service && uv run pytest)
fi

if [[ -f core-api/pom.xml ]]; then
  # core-api serves the AsyncAPI documentation and its tests check it.
  step "AsyncAPI documentation"
  contracts/build-docs.sh

  step "core-api tests"
  (cd core-api && ./mvnw --batch-mode verify)
fi

if [[ -f web/package.json ]]; then
  step "web tests"
  (cd web && npm test)
fi

step "All checks passed"
