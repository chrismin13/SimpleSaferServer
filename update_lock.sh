#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  printf 'Missing uv. Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh\n' >&2
  exit 1
fi

if [[ $# -eq 0 ]]; then
  uv lock --upgrade
else
  for package in "$@"; do
    uv lock --upgrade-package "$package"
  done
fi

uv sync --frozen --group dev
bash check_ci.sh --no-sync --check-format
bash check_security.sh --no-sync
