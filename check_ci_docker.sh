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

# This reproduces the GitHub Actions Quality gates in the same Python image
# used by CI. Keep this strict so a green run means the CI workflow should be green too.
$RUNTIME run --rm \
  --volume "$PWD:/workspace:Z" \
  --workdir /workspace \
  python:3.7-buster \
  bash -lc 'set -euo pipefail; python -m pip install --upgrade "pip<24.1" wheel; python -m pip install -r requirements.txt -r requirements-dev.txt; python -m ruff format --check .; python -m ruff check .; python -m pytest; pyright; python -m bandit -c pyproject.toml -r .; python -m pip_audit -r requirements.txt -r requirements-dev.txt --ignore-vuln GHSA-6w46-j5rx-g56g'
