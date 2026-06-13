#!/usr/bin/env bash
set -euo pipefail

CI_IMAGE="${CI_IMAGE:-ghcr.io/astral-sh/uv:python3.14-trixie}"

CONTAINER_BIN=""
if command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then
  CONTAINER_BIN="podman"
elif command -v docker >/dev/null 2>&1; then
  if ! docker info >/dev/null 2>&1; then
    printf 'Docker is installed, but the daemon is not reachable. Start Docker and rerun this script.\n' >&2
    exit 1
  fi
  CONTAINER_BIN="docker"
else
  printf 'Docker or Podman is required for exact Python CI reproduction.\n' >&2
  exit 1
fi

printf '\n==> Docker CI image: %s\n' "$CI_IMAGE"
exec "$CONTAINER_BIN" run --rm \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -e UV_CACHE_DIR=/tmp/uv-cache \
  -v "$PWD:/work" \
  -w /work \
  "$CI_IMAGE" \
  bash -lc 'set -euo pipefail; bash check_ci.sh --check-format; bash check_security.sh --no-sync'
