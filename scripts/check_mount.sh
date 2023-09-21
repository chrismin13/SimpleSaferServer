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

# Check if the device is mounted
if ! grep -qs $MOUNT_POINT /proc/mounts; then
    # Attempt to mount the device
    if ! mount /dev/disk/by-uuid/$UUID; then
        # If mounting failed, send an email
        send_email "Failed to mount device with UUID $UUID at $MOUNT_POINT" "Mounting Error"
        exit 1
    else
        send_email "Device with UUID $UUID at $MOUNT_POINT was remounted." "Device Remounted"
    fi
else
    echo "Device is mounted"
fi

# Check for I/O Errors
if ! ls $MOUNT_POINT; then
    # Attempt to unmount the device first
    if ! umount $MOUNT_POINT; then
        send_email "Failed to unmount device after IO Errors occured." "IO Error - Failed to unmount"
    fi
    if ! mount /dev/disk/by-uuid/$UUID; then
        # If mounting failed, send an email
        send_email "Failed to mount device with UUID $UUID at $MOUNT_POINT after IO Errors had occured." "Mounting Error due to IO Errors"
        exit 1
    else
        send_email "Device with UUID $UUID at $MOUNT_POINT was remounted after IO Errors had occured." "Device Remounted due to IO Errors"
    fi
else
    echo "No IO Errors have occured"
fi

# If all checks passed, then exit with success
exit 0
