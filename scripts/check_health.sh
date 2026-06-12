#!/bin/bash

set -euo pipefail

PYTHON_BIN="/opt/SimpleSaferServer/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  echo "Missing SimpleSaferServer Python environment at $PYTHON_BIN" >&2
  exit 1
fi

if [ -x "/opt/SimpleSaferServer/scripts/check_health.py" ]; then
  exec "$PYTHON_BIN" "/opt/SimpleSaferServer/scripts/check_health.py"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$PYTHON_BIN" "$SCRIPT_DIR/check_health.py"
