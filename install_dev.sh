#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v uv >/dev/null 2>&1; then
  printf '%s\n' "Missing uv. Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

uv sync --group dev

if ! command -v rclone >/dev/null 2>&1; then
  printf '%s\n' "Note: rclone is not installed. Fake mode will still boot, but MEGA and real cloud backup runs will not work until rclone is available."
fi

PYTHON_VERSION="$(uv run python -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
printf 'Development environment ready in %s/.venv using Python %s.\n' "$SCRIPT_DIR" "$PYTHON_VERSION"
printf '%s\n' "Start fake mode with: bash run_fake.sh"
printf '%s\n' "Optional: install commit hooks with uv run pre-commit install"
printf '%s\n' "To reset fake-mode setup data later, run: bash reset_fake_mode.sh"
