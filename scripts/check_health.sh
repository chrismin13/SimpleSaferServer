#!/bin/bash

set -euo pipefail

if [ -x "/opt/SimpleSaferServer/scripts/check_health.py" ]; then
    exec /usr/bin/python3 "/opt/SimpleSaferServer/scripts/check_health.py"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec /usr/bin/python3 "$SCRIPT_DIR/check_health.py"
