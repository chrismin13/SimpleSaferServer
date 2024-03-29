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

# Prompt for missing variables
declare -A prompts=(
  ["EMAIL_ADDRESS"]="Enter the email address for alerts: "
  ["SERVER_NAME"]="Enter the server name: "
  ["UUID"]="Enter the UUID of the external hard drive (e.g. 2CD49023D48FED80): "
  ["USB_ID"]="Enter the USB ID of the external hard drive (e.g. 0480:a202): "
  ["MOUNT_POINT"]="Enter the mount point of the external hard drive (e.g. /media/backup): "
  ["RCLONE_DIR"]="Enter the backup directory on Rclone (e.g. OneDriveCrypt:): "
  ["BANDWIDTH_LIMIT"]="Optional: Enter a bandwidth limit for the rclone backup (e.g. 4M): "
)

for key in "${!prompts[@]}"; do
  if [ -z "${!key}" ]; then
    read -p "${prompts[$key]}" input
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

# Copy systemd timer files
cp ./timers/* /etc/systemd/system/

# Reload systemd and enable timers
systemctl daemon-reload
systemctl enable --now backup_cloud.timer check_mount.timer check_hdsentinel_health.timer

# Show success message and active timers to ensure installation worked
printf "\nInstallation/Update complete. Your timers now are:\n\n"
systemctl list-timers | cat
