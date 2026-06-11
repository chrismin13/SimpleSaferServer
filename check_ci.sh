#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  printf 'Missing uv. Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh\n' >&2
  exit 1
fi

SYNC=true
CHECK_FORMAT=false
PYTEST_ARGS=()
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
  run_check "Check formatting" uv run ruff format --check .
else
  run_check "Format" uv run ruff format .
fi

run_check "Lint" uv run ruff check .
if [[ ${#PYTEST_ARGS[@]} -eq 0 ]]; then
  run_check "Test" uv run pytest -n "$PYTEST_WORKERS"
else
  run_check "Test" uv run pytest "${PYTEST_ARGS[@]}"
fi
run_check "Type check" uv run ty check

printf '\nFast local checks passed. Run bash check_security.sh before releases or dependency changes.\n'
