#!/bin/bash

CONFIG_FILE="${SSS_CONFIG_FILE:-/etc/SimpleSaferServer/config.conf}"
PYTHON_BIN="${SSS_PYTHON_BIN:-/opt/SimpleSaferServer/.venv/bin/python}"
VALIDATE_STORAGE_SCRIPT="${SSS_VALIDATE_STORAGE_SCRIPT:-/opt/SimpleSaferServer/scripts/validate_storage_source.py}"
LOG_ALERT_SCRIPT="${SSS_LOG_ALERT_SCRIPT:-/opt/SimpleSaferServer/scripts/log_alert.py}"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Missing SimpleSaferServer Python environment at $PYTHON_BIN" >&2
  exit 1
fi

get_config_value() {
  section=$1
  key=$2
  awk -F '=' -v section="[$section]" -v key="$key" '
        $0 == section { in_section=1; next }
        /^\[.*\]/     { in_section=0 }
        in_section && $1 ~ "^[ \t]*"key"[ \t]*$" { gsub(/^[ \t]+|[ \t]+$/, "", $2); print $2; exit }
    ' "$CONFIG_FILE" | tr -d '"'
}

MOUNT_POINT=$(get_config_value backup mount_point)
FROM_ADDRESS=$(get_config_value backup from_address)
EMAIL_ADDRESS=$(get_config_value backup email_address)
SERVER_NAME=$(get_config_value system server_name)
RCLONE_DIR=$(get_config_value backup rclone_dir)
BANDWIDTH_LIMIT=$(get_config_value backup bandwidth_limit)
CLOUD_ENABLED=$(get_config_value backup cloud_enabled)

# Function to send email and log alert
function send_email {
  echo "$1 - $2" # Log the status
  echo -e "Subject: $1 - $SERVER_NAME\nFrom: $FROM_ADDRESS\n\n$2" | msmtp --from="$FROM_ADDRESS" -- "$EMAIL_ADDRESS"
  # Log alert using the standalone script
  "$PYTHON_BIN" "$LOG_ALERT_SCRIPT" "$1" "$2" "error" "backup_cloud"
}

echo "Starting cloud backup process..."

if [ "$CLOUD_ENABLED" = "false" ]; then
  echo "Cloud backup is disabled."
  exit 0
fi
if [ "$CLOUD_ENABLED" != "true" ]; then
  send_email "BACKUP TO CLOUD FAILED - Cloud Backup Setting Invalid" "Cloud backup could not start because backup.cloud_enabled is missing or invalid in $CONFIG_FILE. Save Cloud Backup settings in the web interface."
  exit 1
fi

# rclone sync makes the cloud destination match the local source. If a mount is
# missing and the source folder looks empty, a sync can delete the cloud copy.
# Keep this safety gate immediately before the source checks and sync command.
if [ -x "$VALIDATE_STORAGE_SCRIPT" ]; then
  if ! "$PYTHON_BIN" "$VALIDATE_STORAGE_SCRIPT"; then
    send_email "BACKUP TO CLOUD FAILED - Storage Source Check Failed" "SimpleSaferServer could not verify the storage source at $MOUNT_POINT. Cloud backup was stopped so it would not sync the wrong or empty folder."
    exit 1
  fi
else
  send_email "BACKUP TO CLOUD FAILED - Storage Source Check Missing" "SimpleSaferServer could not find the storage validation helper at $VALIDATE_STORAGE_SCRIPT."
  exit 1
fi

# Check for I/O errors after the marker and write probe pass. This gives older
# installs a familiar broad directory-read failure while the marker check catches
# wrong-source and missing-mount cases first.
if ! ls "$MOUNT_POINT" >/dev/null 2>&1; then
  send_email "BACKUP TO CLOUD FAILED - Drive has IO Errors" "Check the connection to the Hard Drive at $MOUNT_POINT!"
  exit 1
fi

# Check if rclone directory is configured
if [ -z "$RCLONE_DIR" ]; then
  send_email "BACKUP TO CLOUD FAILED - No Rclone Directory Configured" "Please configure the cloud backup destination in the web interface."
  exit 1
fi

# Check if there's a bandwidth limit
if [ -n "$BANDWIDTH_LIMIT" ]; then
  extra_args=(--bwlimit "$BANDWIDTH_LIMIT")
  echo "Using bandwidth limit: $BANDWIDTH_LIMIT"
else
  extra_args=()
fi

echo "Starting cloud backup to $RCLONE_DIR..."
echo "Source: $MOUNT_POINT"
echo "Destination: $RCLONE_DIR"

# Keep the failure branch next to rclone so ShellCheck and future readers do not
# have to track a saved exit code through unrelated lines.
if ! rclone sync "$MOUNT_POINT" "$RCLONE_DIR" --create-empty-src-dirs -v "${extra_args[@]}"; then
  logs=$(journalctl -u backup_cloud.service -n 100 --no-pager 2>/dev/null || echo "Could not retrieve logs")
  send_email "BACKUP TO CLOUD FAILED - Unknown Error" "Backup failed. Recent logs:\n\n$logs"
  exit 1
fi

echo "Cloud backup completed successfully"
exit 0
