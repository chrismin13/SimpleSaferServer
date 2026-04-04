#!/bin/bash
set -euo pipefail

python3 -m venv .venv

".venv/bin/python" -m pip install --upgrade pip wheel
".venv/bin/pip" install -r requirements.txt

if ! command -v rclone >/dev/null 2>&1; then
  printf '%s\n' "Note: rclone is not installed. Fake mode will still boot, but MEGA and real cloud backup runs will not work until rclone is available."
fi

printf '%s\n' "Development environment ready. Start fake mode with: bash run_fake.sh"
printf '%s\n' "To reset fake-mode setup data later, run: bash reset_fake_mode.sh"
