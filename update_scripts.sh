#!/bin/bash
# Update all relevant scripts to /usr/local/bin and set permissions

set -e

SCRIPTS=(
  check_mount.sh
  check_health.sh
  backup_cloud.sh
  predict_health.py
  log_alert.py
)

SRC_DIR="$(dirname "$0")/scripts"
DEST_DIR="/usr/local/bin"

for script in "${SCRIPTS[@]}"; do
  if [ -f "$SRC_DIR/$script" ]; then
    echo "Copying $script to $DEST_DIR..."
    sudo cp "$SRC_DIR/$script" "$DEST_DIR/"
    sudo chmod +x "$DEST_DIR/$script"
  else
    echo "Warning: $SRC_DIR/$script not found. Skipping."
  fi

done

echo "All scripts updated successfully!" 