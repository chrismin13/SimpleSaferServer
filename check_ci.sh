#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  printf 'Missing uv. Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh\n' >&2
  exit 1
fi

SYNC=true
CHECK_FORMAT=false
PYTEST_ARGS=()
# GitHub Actions checks out the repository on the host, then runs this script
# inside a container as a different user. Mark the working tree safe before any
# `git ls-files` call so shell checks cannot be silently skipped.
git config --global --add safe.directory "$PWD" 2>/dev/null || true
# Only check tracked shell scripts. Local virtualenvs and generated test data can
# contain third-party scripts that are not part of this repo's quality gate.
SHELL_FILES_OUTPUT="$(git ls-files '*.sh')" || {
  printf 'Failed to list tracked shell scripts with git ls-files.\n' >&2
  exit 1
}
SHELL_FILES=()
if [[ -n "$SHELL_FILES_OUTPUT" ]]; then
  mapfile -t SHELL_FILES <<<"$SHELL_FILES_OUTPUT"
fi
SHFMT_ARGS=(-i 2 -ci -bn)
# Full-suite runs are the common pre-commit path, so use xdist there. Targeted
# pytest arguments usually mean a developer wants the quickest single-file or
# single-test feedback, where worker startup costs can be slower than serial.
PYTEST_WORKERS="${PYTEST_WORKERS:-auto}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-sync)
      SYNC=false
      shift
      ;;
    --check-format)
      CHECK_FORMAT=true
      shift
      ;;
    --)
      shift
      PYTEST_ARGS+=("$@")
      break
      ;;
    *)
      PYTEST_ARGS+=("$1")
      shift
      ;;
  esac
done

run_check() {
  printf '\n==> %s\n' "$1"
  shift
  "$@"
}

if [[ "$SYNC" == true ]]; then
  run_check "Sync dependencies" uv sync --frozen --group dev
fi

if [[ "$CHECK_FORMAT" == true ]]; then
  run_check "Check Python formatting" uv run ruff format --check .
  if [[ ${#SHELL_FILES[@]} -gt 0 ]]; then
    run_check "Check shell formatting" uv run shfmt -d "${SHFMT_ARGS[@]}" "${SHELL_FILES[@]}"
  fi
else
  run_check "Format Python" uv run ruff format .
  if [[ ${#SHELL_FILES[@]} -gt 0 ]]; then
    run_check "Format shell" uv run shfmt -w "${SHFMT_ARGS[@]}" "${SHELL_FILES[@]}"
  fi
fi

run_check "Lint" uv run ruff check .
if [[ ${#SHELL_FILES[@]} -gt 0 ]]; then
  run_check "Lint shell" bash scripts/run_shellcheck.sh "${SHELL_FILES[@]}"
fi
if [[ ${#PYTEST_ARGS[@]} -eq 0 ]]; then
  run_check "Test" uv run pytest -n "$PYTEST_WORKERS"
else
  run_check "Test" uv run pytest "${PYTEST_ARGS[@]}"
fi
run_check "Type check" uv run ty check

printf '\nFast local checks passed. Run bash check_security.sh before releases or dependency changes.\n'
