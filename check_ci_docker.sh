#!/usr/bin/env bash
set -euo pipefail

# Detect atomic/Fedora Silverblue-style systems and prefer podman when available.
if command -v podman >/dev/null 2>&1; then
  RUNTIME="podman"
  if ! podman info >/dev/null 2>&1; then
    printf 'Podman is installed, but the daemon is not reachable. Start Podman and rerun this script.\n' >&2
    exit 1
  fi
elif command -v docker >/dev/null 2>&1; then
  RUNTIME="docker"
  if ! docker info >/dev/null 2>&1; then
    printf 'Docker is installed, but the daemon is not reachable. Start Docker and rerun this script.\n' >&2
    exit 1
  fi
else
  printf 'Docker or Podman is required for exact Python 3.7 CI reproduction.\n' >&2
  exit 1
fi

MODE="${1:-all}"
if [[ "$MODE" != "all" && "$MODE" != "modern" && "$MODE" != "legacy-python37" ]]; then
  printf 'Usage: bash check_ci_docker.sh [all|modern|legacy-python37]\n' >&2
  exit 1
fi

run_lane() {
  local mode="$1"
  local image=""
  local requirements=""
  local pip_upgrade=""
  local final_gate=""

  if [[ "$mode" == "legacy-python37" ]]; then
    image="python:3.7-buster"
    requirements="requirements-legacy-py37.txt"
    pip_upgrade='"pip<24.1" wheel'
    final_gate="python - <<'PY'
import ast
from pathlib import Path

for path in sorted(Path(\".\").rglob(\"*.py\")):
    if any(part in {\".venv\", \".git\", \"__pycache__\"} for part in path.parts):
        continue
    source = path.read_text(encoding=\"utf-8\")
    ast.parse(source, filename=str(path))
PY"
  else
    image="python:3.13-trixie"
    requirements="requirements.txt"
    pip_upgrade="pip wheel"
    final_gate="python -m pip_audit -r requirements.txt -r requirements-dev.txt"
  fi

  printf '\n==> Docker CI lane: %s (%s)\n' "$mode" "$image"
  $RUNTIME run --rm \
    --volume "$PWD:/workspace:Z" \
    --workdir /workspace \
    "$image" \
    bash -lc "set -euo pipefail; python -m pip install --upgrade $pip_upgrade; python -m pip install -r $requirements -r requirements-dev.txt; python -m ruff format --check .; python -m ruff check .; python -m pytest; pyright; python -m bandit -c pyproject.toml -r .; $final_gate"
}

# This reproduces the GitHub Actions Quality gates in the same Python images
# used by CI. Keep this strict so a green default run covers the modern
# security lane and the Python 3.7 compatibility lane.
if [[ "$MODE" == "all" ]]; then
  run_lane "modern"
  run_lane "legacy-python37"
else
  run_lane "$MODE"
fi
