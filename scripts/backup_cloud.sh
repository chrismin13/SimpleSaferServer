#!/bin/bash

CONFIG_FILE="/etc/SimpleSaferServer/config.conf"
CONFIG_DIR="/etc/SimpleSaferServer"
RCLONE_INCLUDE_PATTERNS_FILE="$CONFIG_DIR/rclone_include_patterns.txt"
RCLONE_EXCLUDE_PATTERNS_FILE="$CONFIG_DIR/rclone_exclude_patterns.txt"
PYTHON_BIN="/opt/SimpleSaferServer/.venv/bin/python"
FILTER_FILE=""
FILTER_RULE_COUNT=0
INCLUDE_RULE_COUNT=0

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

cleanup_filter_file() {
  if [ -n "$FILTER_FILE" ] && [ -f "$FILTER_FILE" ]; then
    rm -f "$FILTER_FILE"
  fi
}

append_filter_patterns() {
  local rule_prefix=$1
  local pattern_file=$2
  local pattern
  local trimmed

  [ -f "$pattern_file" ] || return 0

  while IFS= read -r pattern || [ -n "$pattern" ]; do
    trimmed=$pattern
    trimmed="${trimmed#"${trimmed%%[![:space:]]*}"}"
    trimmed="${trimmed%"${trimmed##*[![:space:]]}"}"
    if [ -z "$trimmed" ] || [[ "$trimmed" == \#* ]] || [[ "$trimmed" == \;* ]]; then
      continue
    fi
    printf "%s %s\n" "$rule_prefix" "$trimmed" >>"$FILTER_FILE"
    FILTER_RULE_COUNT=$((FILTER_RULE_COUNT + 1))
    if [ "$rule_prefix" = "+" ]; then
      INCLUDE_RULE_COUNT=$((INCLUDE_RULE_COUNT + 1))
    fi
  done <"$pattern_file"
}

add_rclone_filter_args() {
  FILTER_FILE=$(mktemp)
  append_filter_patterns "-" "$RCLONE_EXCLUDE_PATTERNS_FILE"
  append_filter_patterns "+" "$RCLONE_INCLUDE_PATTERNS_FILE"

  if [ "$INCLUDE_RULE_COUNT" -gt 0 ]; then
    # rclone --filter-from reads rules in order. With include rules present,
    # this final rule makes the include list act like an allow-list.
    printf "%s\n" "- **" >>"$FILTER_FILE"
    FILTER_RULE_COUNT=$((FILTER_RULE_COUNT + 1))
  fi

  if [ "$FILTER_RULE_COUNT" -gt 0 ]; then
    extra_args+=(--filter-from "$FILTER_FILE")
    echo "Using configured rclone file filters."
  else
    cleanup_filter_file
    FILTER_FILE=""
  fi
}

trap cleanup_filter_file EXIT

MOUNT_POINT=$(get_config_value backup mount_point)
FROM_ADDRESS=$(get_config_value backup from_address)
EMAIL_ADDRESS=$(get_config_value backup email_address)
SERVER_NAME=$(get_config_value system server_name)
RCLONE_DIR=$(get_config_value backup rclone_dir)
BANDWIDTH_LIMIT=$(get_config_value backup bandwidth_limit)

# Function to send email and log alert
function send_email {
  echo "$1 - $2" # Log the status
  echo -e "Subject: $1 - $SERVER_NAME\nFrom: $FROM_ADDRESS\n\n$2" | msmtp --from="$FROM_ADDRESS" -- "$EMAIL_ADDRESS"
  # Log alert using the standalone script
  "$PYTHON_BIN" /opt/SimpleSaferServer/scripts/log_alert.py "$1" "$2" "error" "backup_cloud"
}

echo "Starting cloud backup process..."

# Check if drive is mounted
if ! grep -qs "$MOUNT_POINT" /proc/mounts; then
  send_email "BACKUP TO CLOUD FAILED - Drive Disconnected" "Check the connection to the Hard Drive at $MOUNT_POINT!"
  exit 1
fi

# Check for I/O Errors
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

add_rclone_filter_args

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
