#!/bin/bash

APP_DIR="/opt/SimpleSaferServer"
PYTHON_BIN="$APP_DIR/venv/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="/usr/bin/python3"
fi

cd "$APP_DIR" || exit 1
exec "$PYTHON_BIN" "$APP_DIR/scripts/app_update.py"
