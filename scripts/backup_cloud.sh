#!/bin/bash

CONFIG_FILE="/etc/SimpleSaferServer/config.conf"

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

# Function to send email and log alert
function send_email {
    echo "$1 - $2" # Log the status
    echo -e "Subject: $1 - $SERVER_NAME\nFrom: $FROM_ADDRESS\n\n$2" | msmtp --from=$FROM_ADDRESS $EMAIL_ADDRESS
    # Log alert using the standalone script
    python3 /opt/SimpleSaferServer/scripts/log_alert.py "$1" "$2" "error" "backup_cloud"
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
    extra_args="--bwlimit $BANDWIDTH_LIMIT"
    echo "Using bandwidth limit: $BANDWIDTH_LIMIT"
else
    extra_args=""
fi

# Run rclone sync
echo "Starting cloud backup to $RCLONE_DIR..."
echo "Source: $MOUNT_POINT"
echo "Destination: $RCLONE_DIR"

rclone sync "$MOUNT_POINT" "$RCLONE_DIR" --create-empty-src-dirs -v $extra_args

# Check if backup was successful
if [ $? -ne 0 ]; then
    logs=$(journalctl -u backup_cloud.service -n 100 --no-pager 2>/dev/null || echo "Could not retrieve logs")
    send_email "BACKUP TO CLOUD FAILED - Unknown Error" "Backup failed. Recent logs:\n\n$logs"
    exit 1
fi

echo "Cloud backup completed successfully"
exit 0 