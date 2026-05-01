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

# Mirrors the Python 3.13 security lane in .github/workflows/python-ci.yml for local,
# intentional pre-push checks. Python 3.7 compatibility has a separate Docker
# path because several fixed dependency releases no longer install on 3.7.
run_check "Check formatting" .venv/bin/python -m ruff format --check .
run_check "Lint" .venv/bin/python -m ruff check .
run_check "Test" .venv/bin/python -m pytest
run_check "Type check" .venv/bin/pyright
run_check "Security scan" .venv/bin/python -m bandit -c pyproject.toml -r .
run_check "Dependency audit" .venv/bin/python -m pip_audit -r requirements.txt -r requirements-dev.txt

printf '\nLocal CI checks passed.\n'
