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

get_mount_points() {
  "$PYTHON_BIN" - "$CONFIG_FILE" <<'PY'
import configparser
import json
import re
import sys

config = configparser.ConfigParser()
config.read(sys.argv[1])

primary = config.get("backup", "mount_point", fallback="").strip()
raw_extra = config.get("backup", "additional_mount_points", fallback="").strip()

mount_points = []
seen = set()
for path in [primary]:
    if path and path not in seen:
        mount_points.append(path)
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
            mount_points.append(path)
            seen.add(path)

for mount_point in mount_points:
    print(mount_point)
PY
}

USB_ID=$(get_config_value backup usb_id)
FROM_ADDRESS=$(get_config_value backup from_address)
EMAIL_ADDRESS=$(get_config_value backup email_address)
SERVER_NAME=$(get_config_value system server_name)

# Function to send email and log alert
function send_email {
  echo "$1 - $2" # Log the status
  echo -e "Subject: $1 - $SERVER_NAME\nFrom: $FROM_ADDRESS\n\n$2" | msmtp --from="$FROM_ADDRESS" -- "$EMAIL_ADDRESS"
  # Log alert using the standalone script
  "$PYTHON_BIN" /opt/SimpleSaferServer/scripts/log_alert.py "$1" "$2" "error" "check_mount"
}

echo "Checking if the backup drive is available."

mapfile -t MOUNT_POINTS < <(get_mount_points)
if [ "${#MOUNT_POINTS[@]}" -eq 0 ]; then
  send_email "No backup mount point is configured" "Mount Configuration Error"
  exit 1
fi

# Check if the device is plugged in (only if USB_ID is set)
if [ -n "$USB_ID" ]; then
  echo "Checking if the USB device is plugged in."
  if ! lsusb | grep -F -q -- "$USB_ID"; then
    send_email "USB device with ID $USB_ID is not plugged in" "USB Device Error"
    exit 1
  else
    echo "USB device with ID $USB_ID is plugged in"
  fi
else
  echo "No USB_ID configured, skipping USB device check"
fi

for mount_point in "${MOUNT_POINTS[@]}"; do
  echo "Checking if the device is mounted at $mount_point."

  # Each configured source must have a systemd mount unit, usually generated
  # from /etc/fstab. SimpleSaferServer only creates that entry for the primary
  # backup drive; extra sources are deliberately admin-managed for now.
  SYSTEMD_MOUNT_UNIT="$(systemd-escape -p --suffix=mount "$mount_point")"

  if ! systemctl is-active --quiet "$SYSTEMD_MOUNT_UNIT"; then
    if ! systemctl start "$SYSTEMD_MOUNT_UNIT"; then
      send_email "Failed to mount device at $mount_point ($SYSTEMD_MOUNT_UNIT)" "Mounting Error"
      exit 1
    else
      send_email "Device at $mount_point ($SYSTEMD_MOUNT_UNIT) was remounted." "Device Remounted"
    fi
  else
    echo "Device is mounted at $mount_point"
  fi

  if ! ls "$mount_point" >/dev/null 2>&1; then
    if ! systemctl stop "$SYSTEMD_MOUNT_UNIT"; then
      send_email "Failed to unmount device at $mount_point after IO Errors occurred." "IO Error - Failed to unmount"
    fi
    if ! systemctl start "$SYSTEMD_MOUNT_UNIT"; then
      send_email "Failed to mount device at $mount_point after IO Errors had occurred." "Mounting Error due to IO Errors"
      exit 1
    else
      send_email "Device at $mount_point ($SYSTEMD_MOUNT_UNIT) was remounted after IO Errors had occurred." "Device Remounted due to IO Errors"
    fi
  else
    echo "No IO Errors have occurred at $mount_point"
  fi
done

# If all checks passed, then exit with success
echo "Mount check completed successfully"
exit 0
