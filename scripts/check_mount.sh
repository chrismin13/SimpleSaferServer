#!/bin/bash

# Source the config file
source /etc/SimpleSaferServer/config.conf

# Function to send email
function send_email {
    echo "$1 - $2" # Log the status
    echo -e "Subject: $1 - $SERVER_NAME\n$2" | msmtp $EMAIL_ADDRESS
}

echo "Checking if the USB device is plugged in."

# Check if the device is plugged in
if ! lsusb | grep -q $USB_ID; then
    send_email "USB device with ID $USB_ID is not plugged in" "USB Device Error"
    exit 1
else
    echo "USB device with ID $USB_ID is plugged in"
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
if ! ls $MOUNT_POINT; then
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
exit 0
