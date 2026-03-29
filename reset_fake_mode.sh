#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
FAKE_DATA_DIR="$REPO_ROOT/.dev-data"

if [ ! -d "$FAKE_DATA_DIR" ]; then
  printf '%s\n' "No fake-mode data found at $FAKE_DATA_DIR"
  exit 0
fi

printf '%s\n' "This will permanently delete fake-mode data in:"
printf '%s\n' "  $FAKE_DATA_DIR"
printf '%s' "Continue? [y/N] "
read -r response

case "$response" in
  y|Y|yes|YES)
    rm -rf "$FAKE_DATA_DIR"
    printf '%s\n' "Fake-mode data reset complete."
    ;;
  *)
    printf '%s\n' "Cancelled."
    exit 1
    ;;
esac
