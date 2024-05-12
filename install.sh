#!/bin/bash

# Check if script is running as root
if [ "$EUID" -ne 0 ]; then
  printf "\nThis script must be run as root. Attempting to elevate privilege...\n"
  exec sudo bash "$0" "$@"
fi

printf "\nWelcome to the Simple Safer Server script collection installer.\n\n"

# Get the username of the user who invoked sudo
invoked_user=$(logname)
config_path="/etc/SimpleSaferServer/config.conf"

# Create config directory if it doesn't exist
mkdir -p $(dirname "$config_path")

# Load existing configurations
if [ -f "$config_path" ]; then
  source $config_path
fi

# Define the order and prompts in separate arrays
order=("EMAIL_ADDRESS" "SERVER_NAME" "UUID" "USB_ID" "MOUNT_POINT" "RCLONE_DIR" "BANDWIDTH_LIMIT" "CHECK_HDSENTINEL_HEALTH_TIME" "CHECK_MOUNT_TIME" "BACKUP_CLOUD_TIME")
prompts=(
  "Enter the email address for alerts: "
  "Enter the server name: "
  "Enter the UUID of the external hard drive (e.g. 2CD49023D48FED80): "
  "Enter the USB ID of the external hard drive (e.g. 0480:a202): "
  "Enter the mount point of the external hard drive (e.g. /media/backup): "
  "Enter the backup directory on Rclone (e.g. OneDriveCrypt:): "
  "Optional: Enter a bandwidth limit for the rclone backup (e.g. 4M): "
  "You will now be asked to enter a time for the scheduled tasks. Use a time when the server and network won't be in use to avoid interruptions. Keep the tasks separated from each other, e.g first at 2:49, next at 2:50 and final at 3:00. Enter the start time for checking HD Sentinel health (e.g. 2:49:00): "
  "Enter the start time for checking if the disk is mounted (e.g. 2:50:00): "
  "Enter the start time for the cloud backup (e.g. 3:00:00): "
)

# Prompt for missing variables based on the order
for i in "${!order[@]}"; do
  key=${order[i]}
  prompt=${prompts[i]}
  current_value=$(eval echo \$$key)
  if [ -z "$current_value" ]; then
    read -p "$prompt" input
    eval $key='$input'
  fi
done


# Update or create config file
cat <<EOL >"$config_path"
USERNAME="$invoked_user"
EMAIL_ADDRESS="$EMAIL_ADDRESS"
SERVER_NAME="$SERVER_NAME"
UUID="$UUID"
USB_ID="$USB_ID"
MOUNT_POINT="$MOUNT_POINT"
RCLONE_DIR="$RCLONE_DIR"
BANDWIDTH_LIMIT="$BANDWIDTH_LIMIT"
CHECK_HDSENTINEL_HEALTH_TIME="$CHECK_HDSENTINEL_HEALTH_TIME"
CHECK_MOUNT_TIME="$CHECK_MOUNT_TIME"
BACKUP_CLOUD_TIME="$BACKUP_CLOUD_TIME"
EOL

# TODO: Add a menu for script selection here
# ...

# Copy scripts to /usr/local/bin
cp ./scripts/* /usr/local/bin/

# Make scripts executable
chmod +x /usr/local/bin/*.sh

# Modify .service files to include the proper username and group, then copy them to /etc/systemd/system/
for f in ./services/*.service; do
  sed -e "s/__USER__/$invoked_user/g" -e "s/__GROUP__/$invoked_user/g" "$f" >"/etc/systemd/system/$(basename $f)"
done

# Modify .timer files to include the correct time, then copy them to /etc/systemd/system/
for f in ./timers/*.timer; do
  sed -e "s/__CHECK_HDSENTINEL_HEALTH_TIME__/$CHECK_HDSENTINEL_HEALTH_TIME/g" \
      -e "s/__CHECK_MOUNT_TIME__/$CHECK_MOUNT_TIME/g" \
      -e "s/__BACKUP_CLOUD_TIME__/$BACKUP_CLOUD_TIME/g" "$f" >"/etc/systemd/system/$(basename $f)"
done


# Reload systemd and enable timers
systemctl daemon-reload
systemctl enable --now backup_cloud.timer check_mount.timer check_hdsentinel_health.timer

# Show success message and active timers to ensure installation worked
printf "\nInstallation/Update complete. Your timers now are:\n\n"
systemctl list-timers | cat
