#!/bin/bash

CONFIG_FILE="/etc/SimpleSaferServer/config.conf"
PYTHON_BIN="/opt/SimpleSaferServer/.venv/bin/python"

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

get_backup_sources() {
  "$PYTHON_BIN" - "$CONFIG_FILE" <<'PY'
import configparser
import json
import re
import sys

config = configparser.ConfigParser()
config.read(sys.argv[1])

primary = config.get("backup", "mount_point", fallback="").strip()
raw_extra = config.get("backup", "additional_mount_points", fallback="").strip()

sources = []
seen = set()
for path in [primary]:
    if path and path not in seen:
        sources.append(path)
        seen.add(path)

if raw_extra:
    try:
        parsed = json.loads(raw_extra)
    except json.JSONDecodeError:
        parsed = re.split(r"[\n,]", raw_extra)
    if not isinstance(parsed, list):
        parsed = [parsed]
    for value in parsed:
        path = str(value).strip()
        if path and path not in seen:
            sources.append(path)
            seen.add(path)

for source in sources:
    print(source)
PY
}

remote_child_path() {
  local base=$1
  local child=$2
  base=${base%/}
  echo "$base/$child"
}

source_remote_name() {
  local source=$1
  local name
  name=$(printf '%s' "${source#/}" | sed 's#[^A-Za-z0-9._-]#-#g; s#-\+#-#g; s#^-##; s#-$##')
  if [ -z "$name" ]; then
    echo "root"
  else
    echo "$name"
  fi
}

validate_backup_source() {
  local source=$1
  if ! findmnt --mountpoint "$source" >/dev/null 2>&1; then
    send_email "BACKUP TO CLOUD FAILED - Drive Disconnected" "Check the connection to the mounted source at $source!"
    exit 1
  fi

  if ! ls "$source" >/dev/null 2>&1; then
    send_email "BACKUP TO CLOUD FAILED - Drive has IO Errors" "Check the connection to the mounted source at $source!"
    exit 1
  fi
}

sync_backup_source() {
  local source=$1
  local destination=$2

  echo "Source: $source"
  echo "Destination: $destination"

  # Keep the failure branch next to rclone so ShellCheck and future readers do not
  # have to track a saved exit code through unrelated lines.
  if ! rclone sync "$source" "$destination" --create-empty-src-dirs -v "${extra_args[@]}"; then
    logs=$(journalctl -u backup_cloud.service -n 100 --no-pager 2>/dev/null || echo "Could not retrieve logs")
    send_email "BACKUP TO CLOUD FAILED - Unknown Error" "Backup failed while syncing $source to $destination. Recent logs:\n\n$logs"
    exit 1
  fi
}

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

mapfile -t BACKUP_SOURCES < <(get_backup_sources)
if [ "${#BACKUP_SOURCES[@]}" -eq 0 ]; then
  send_email "BACKUP TO CLOUD FAILED - No Backup Source Configured" "Please configure at least one local backup source."
  exit 1
fi

for source in "${BACKUP_SOURCES[@]}"; do
  validate_backup_source "$source"
done

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
sync_backup_source "${BACKUP_SOURCES[0]}" "$RCLONE_DIR"

if [ "${#BACKUP_SOURCES[@]}" -gt 1 ]; then
  echo "Syncing additional mounted sources under $RCLONE_DIR/mounted-sources/..."
  for source in "${BACKUP_SOURCES[@]:1}"; do
    destination=$(remote_child_path "$RCLONE_DIR" "mounted-sources/$(source_remote_name "$source")")
    sync_backup_source "$source" "$destination"
  done
fi

echo "Cloud backup completed successfully"
exit 0
