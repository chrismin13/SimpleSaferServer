#!/bin/bash
set -euo pipefail

export SSS_MODE=fake
export SSS_SKIP_LOGIN="${SSS_SKIP_LOGIN:-true}"

HOST="${SSS_HOST:-127.0.0.1}"
PORT="${SSS_PORT:-5001}"

if [ ! -x ".venv/bin/python" ]; then
  printf '%s\n' "Missing .venv. Run: bash install_dev.sh"
  exit 1
fi

exec .venv/bin/python app.py --host "$HOST" --port "$PORT" --debug
