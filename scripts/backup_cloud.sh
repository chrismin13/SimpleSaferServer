#!/bin/bash
#
# Backup script to encrypted OneDrive storage with rclone #
#

# Source the config file
source /etc/SimpleSaferServer/config.conf

## backup files ##

if grep -qs "$MOUNT_POINT" /proc/mounts; then
  echo "Drive is mounted"
else
  echo "ERROR: DRIVE IS NOT MOUNTED"
  echo -e "Subject: BACKUP TO CLOUD FAILED - Drive Disconnected - $SERVER_NAME\nCheck the connection to the Hard Drive!" | msmtp $EMAIL_ADDRESS
  exit 1
fi

# Check if there's a bandwith limit
if [ -n "$BANDWIDTH_LIMIT" ]; then
  extra_args="--bwlimit $BANDWIDTH_LIMIT" # e.g. --bwlimit 4M will limit the speed to 4mbps
fi

# Run rclone. The arguments are:
# --create-empty-src-dirs: Copies empty folders
# -v: Keeps a log of all the changes and reports progress every minute
# $extra_args: Whatever was set above
rclone sync "$MOUNT_POINT" "$RCLONE_DIR" --create-empty-src-dirs -v $extra_args

## send email in case of error ##
if [ $? -ne 0 ]; then
  logs=$(journalctl -u backup-cloud.service -n 100)
  echo "ERROR: BACKUP FAILED"
  echo -e "Subject: BACKUP TO CLOUD FAILED - Unknown Error - $SERVER_NAME\n$logs" | msmtp $EMAIL_ADDRESS
  exit 1
fi
