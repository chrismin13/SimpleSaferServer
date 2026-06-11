#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  printf 'Missing uv. Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh\n' >&2
  exit 1
fi

SYNC=true
if [[ "${1:-}" == "--no-sync" ]]; then
  SYNC=false
  shift
fi

if [[ $# -gt 0 ]]; then
  printf 'Unknown arguments: %s\n' "$*" >&2
  exit 2
fi

run_check() {
  printf '\n==> %s\n' "$1"
  shift
  "$@"
}

if [[ "$SYNC" == true ]]; then
  run_check "Sync dependencies" uv sync --frozen --group dev
fi

run_check "Security scan" uv run bandit -c pyproject.toml -r .
run_check "Dependency audit" uv run pip-audit --local

printf '\nSecurity checks passed.\n'
