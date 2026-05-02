#!/bin/bash
set -euo pipefail

python3 -m venv .venv

# pip 24.1 dropped support for legacy dependency specifiers that some Debian
# 10/Python 3.7-compatible packages still expose, so keep the dev bootstrap on
# the last pip release that can resolve both repository requirement lanes.
".venv/bin/python" -m pip install --upgrade "pip<24.1" wheel
".venv/bin/pip" install -r requirements.txt
".venv/bin/pip" install -r requirements-dev.txt

if ! command -v rclone >/dev/null 2>&1; then
  printf '%s\n' "Note: rclone is not installed. Fake mode will still boot, but MEGA and real cloud backup runs will not work until rclone is available."
fi

printf '%s\n' "Development environment ready. Start fake mode with: bash run_fake.sh"
printf '%s\n' "Optional: install commit hooks with .venv/bin/pre-commit install"
printf '%s\n' "To reset fake-mode setup data later, run: bash reset_fake_mode.sh"
