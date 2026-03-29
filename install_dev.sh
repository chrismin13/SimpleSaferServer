#!/bin/bash
set -euo pipefail

WITH_ML=0

for arg in "$@"; do
  case "$arg" in
    --with-ml)
      WITH_ML=1
      ;;
    *)
      printf '%s\n' "Unknown argument: $arg"
      printf '%s\n' "Usage: bash install_dev.sh [--with-ml]"
      exit 1
      ;;
  esac
done

python3 -m venv .venv

".venv/bin/python" -m pip install --upgrade pip wheel
".venv/bin/pip" install -r requirements-dev.txt

if [ "$WITH_ML" -eq 1 ]; then
  ".venv/bin/pip" install -r requirements-ml.txt
fi

if ! command -v rclone >/dev/null 2>&1; then
  printf '%s\n' "Note: rclone is not installed. Fake mode will still boot, but MEGA and real cloud backup runs will not work until rclone is available."
fi

if [ "$WITH_ML" -eq 0 ]; then
  printf '%s\n' "Skipped optional ML dependencies. Drive health predictions will use the fake-mode fallback unless you reinstall with --with-ml."
fi

printf '%s\n' "Development environment ready. Start fake mode with: bash run_fake.sh"
printf '%s\n' "To reset fake-mode setup data later, run: bash reset_fake_mode.sh"
