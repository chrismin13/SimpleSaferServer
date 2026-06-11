#!/bin/bash

APP_DIR="/opt/SimpleSaferServer"
PYTHON_BIN="$APP_DIR/.venv/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
    echo "Missing SimpleSaferServer Python environment at $PYTHON_BIN" >&2
    exit 1
fi

cd "$APP_DIR" || exit 1
exec "$PYTHON_BIN" "$APP_DIR/scripts/app_update.py"
