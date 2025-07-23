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
UUID=$(get_config_value backup uuid)
USB_ID=$(get_config_value backup usb_id)
EMAIL_ADDRESS=$(get_config_value backup email_address)
SERVER_NAME=$(get_config_value system server_name)

# Function to send email and log alert
function send_email {
    echo "$1 - $2" # Log the status
    echo -e "Subject: $1 - $SERVER_NAME\nFrom: $EMAIL_ADDRESS\n\n$2" | msmtp $EMAIL_ADDRESS
    
    # Log alert using the standalone script
    python3 /opt/SimpleSaferServer/scripts/log_alert.py "$1" "$2" "error" "check_mount"
}

echo "Checking if the backup drive is available."

# Check if the device is plugged in (only if USB_ID is set)
if [ -n "$USB_ID" ]; then
    echo "Checking if the USB device is plugged in."
    if ! lsusb | grep -q $USB_ID; then
        send_email "USB device with ID $USB_ID is not plugged in" "USB Device Error"
        exit 1
    else
        echo "USB device with ID $USB_ID is plugged in"
    fi
else
    echo "No USB_ID configured, skipping USB device check"
fi

echo "Checking if the device is mounted."

# Systemd mount unit name (modify this to match your mount point)
SYSTEMD_MOUNT_UNIT="$(systemd-escape -p --suffix=mount "$MOUNT_POINT")"

# Check if the device is mounted
if ! systemctl is-active --quiet "$SYSTEMD_MOUNT_UNIT"; then
    # Attempt to mount the device
    if ! systemctl start "$SYSTEMD_MOUNT_UNIT"; then
        # If mounting failed, send an email
        send_email "Failed to mount device at $MOUNT_POINT ($SYSTEMD_MOUNT_UNIT)" "Mounting Error"
        exit 1
    else
        send_email "Device at $MOUNT_POINT ($SYSTEMD_MOUNT_UNIT) was remounted." "Device Remounted"
    fi
else
    echo "Device is mounted"
fi

# Check for I/O Errors
if ! ls "$MOUNT_POINT" >/dev/null 2>&1; then
    # Attempt to unmount the device first
    if ! systemctl stop "$SYSTEMD_MOUNT_UNIT"; then
        send_email "Failed to unmount device at $MOUNT_POINT after IO Errors occurred." "IO Error - Failed to unmount"
    fi
    if ! systemctl start "$SYSTEMD_MOUNT_UNIT"; then
        # If mounting failed, send an email
        send_email "Failed to mount device at $MOUNT_POINT after IO Errors had occurred." "Mounting Error due to IO Errors"
        exit 1
    else
        send_email "Device at $MOUNT_POINT ($SYSTEMD_MOUNT_UNIT) was remounted after IO Errors had occurred." "Device Remounted due to IO Errors"
    fi
else
    echo "No IO Errors have occurred"
fi

# If all checks passed, then exit with success
echo "Mount check completed successfully"
exit 0 