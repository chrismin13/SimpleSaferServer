#!/usr/bin/env bash
set -euo pipefail

if [[ ! -x .venv/bin/python ]]; then
  printf 'Missing .venv. Run bash install_dev.sh first.\n' >&2
  exit 1
fi

run_check() {
  printf '\n==> %s\n' "$1"
  shift
  "$@"
}

run_advisory_check() {
  label="$1"
  printf '\n==> %s (advisory)\n' "$label"
  shift
  if ! "$@"; then
    ADVISORY_FAILURES=$((ADVISORY_FAILURES + 1))
    printf 'Advisory check failed: %s\n' "$label" >&2
  fi
}

ADVISORY_FAILURES=0

# Mirrors .github/workflows/quality.yml for local, intentional pre-push checks.
# GitHub CI runs in Python 3.7; this script uses the active project venv.
run_check "Check formatting" .venv/bin/python -m ruff format --check .
run_check "Lint" .venv/bin/python -m ruff check .
run_check "Test" .venv/bin/python -m pytest
run_advisory_check "Type check" .venv/bin/pyright
run_advisory_check "Security scan" .venv/bin/python -m bandit -c pyproject.toml -r .
run_advisory_check "Dependency audit" .venv/bin/python -m pip_audit -r requirements.txt -r requirements-dev.txt --ignore-vuln GHSA-6w46-j5rx-g56g

if [[ "$ADVISORY_FAILURES" -gt 0 ]]; then
  printf '\nRequired local CI checks passed. %s advisory check(s) reported issues.\n' "$ADVISORY_FAILURES"
else
  printf '\nLocal CI checks passed.\n'
fi
