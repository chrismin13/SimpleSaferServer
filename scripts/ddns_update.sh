#!/bin/bash

set -euo pipefail

PYTHON_BIN="/opt/SimpleSaferServer/venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="/usr/bin/python3"
fi

if [ -x "/opt/SimpleSaferServer/scripts/ddns_update.py" ]; then
    exec "$PYTHON_BIN" "/opt/SimpleSaferServer/scripts/ddns_update.py"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$PYTHON_BIN" "$SCRIPT_DIR/ddns_update.py"
