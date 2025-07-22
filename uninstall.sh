#!/bin/bash

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
NC='\033[0m' # No Color

clear
echo -e "${BLUE}==============================================="
echo -e "   SimpleSaferServer Uninstaller"
echo -e "===============================================${NC}\n"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}ERROR:${NC} Please run as root (sudo)"
    exit 1
fi

echo -e "${YELLOW}WARNING:${NC} This will permanently remove all SimpleSaferServer files, configuration, logs, and user data."
echo -e "${YELLOW}This process is irreversible. Back up any important data before continuing.${NC}\n"
read -p "Are you sure you want to uninstall SimpleSaferServer? [y/N]: " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}Uninstallation cancelled. No changes were made.${NC}"
    exit 0
fi

echo -e "${BLUE}Proceeding with uninstallation...${NC}\n"

echo "Starting SimpleSaferServer uninstallation..."

# Create backup of current smb.conf before uninstalling
SMB_CONF="/etc/samba/smb.conf"
if [ -f "$SMB_CONF" ]; then
    TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
    CURRENT_BACKUP="/etc/samba/smb.conf.uninstall_backup.${TIMESTAMP}"
    echo "Creating backup of current smb.conf: $CURRENT_BACKUP"
    cp "$SMB_CONF" "$CURRENT_BACKUP"
    echo "Backup created successfully."
fi

# Stop and disable background systemd services and timers
for svc in check_mount check_health backup_cloud; do
    echo "Stopping and disabling $svc.service and $svc.timer..."
    systemctl stop ${svc}.timer 2>/dev/null
    systemctl stop ${svc}.service 2>/dev/null
    systemctl disable ${svc}.timer 2>/dev/null
    systemctl disable ${svc}.service 2>/dev/null
    rm -f /etc/systemd/system/${svc}.service
    rm -f /etc/systemd/system/${svc}.timer
    echo "$svc.service and $svc.timer removed."
done

# Stop and remove the web UI systemd service
WEB_SERVICE="simple_safer_server_web.service"
echo "Stopping and disabling $WEB_SERVICE..."
systemctl stop $WEB_SERVICE 2>/dev/null
systemctl disable $WEB_SERVICE 2>/dev/null
rm -f /etc/systemd/system/$WEB_SERVICE

# Clean up SMB configuration
echo "Cleaning up SMB configuration..."
if [ -f "$SMB_CONF" ]; then
    # Remove SimpleSaferServer shares and configurations
    echo "Removing SimpleSaferServer shares and configurations..."
    
    # Create a clean version without SimpleSaferServer blocks
    awk '
    /^# BEGIN SimpleSaferServer$/ { in_block = 1; next }
    /^# END SimpleSaferServer$/ { in_block = 0; next }
    !in_block { print }
    ' "$SMB_CONF" > /tmp/smb.conf.clean
    
    # Also remove any standalone SimpleSaferServer shares that might exist
    # (in case the new SMB manager was used)
    awk '
    /^\[backup\]$/ { in_share = 1; next }
    /^\[.*\]$/ { in_share = 0; print; next }
    !in_share { print }
    ' /tmp/smb.conf.clean > /tmp/smb.conf.final
    
    # Restore the default 'map to guest = bad user' if it was removed
    if ! grep -q "map to guest = bad user" /tmp/smb.conf.final; then
        # Find the [global] section and add the default line after it
        sed '/^\[global\]$/a\   map to guest = bad user' /tmp/smb.conf.final > /tmp/smb.conf.restored
        mv /tmp/smb.conf.restored /tmp/smb.conf.final
    fi
    
    mv /tmp/smb.conf.final "$SMB_CONF"
    echo "SimpleSaferServer configurations removed from smb.conf."
    
    # Restart SMB services
    echo "Restarting SMB services..."
    systemctl restart smbd 2>/dev/null
    systemctl restart nmbd 2>/dev/null
    echo "SMB services restarted."
fi

# Remove scripts installed to /usr/local/bin from scripts/
echo "Removing scripts from /usr/local/bin..."
for script in check_mount.sh check_health.sh backup_cloud.sh predict_health.py log_alert.py; do
    rm -f /usr/local/bin/$script
    echo "/usr/local/bin/$script removed."
done
# Remove any other SimpleSaferServer-related scripts
find /usr/local/bin -maxdepth 1 -type f \( -name 'check_mount.sh' -o -name 'check_health.sh' -o -name 'backup_cloud.sh' -o -name 'predict_health.py' -o -name 'log_alert.py' \) -exec rm -f {} \;

# Remove model files from legacy and new locations
rm -f /usr/local/bin/xgb_model.json
rm -f /usr/local/bin/optimal_threshold_xgb.pkl
echo "/usr/local/bin/xgb_model.json and /usr/local/bin/optimal_threshold_xgb.pkl removed if present."
echo "Removing /usr/local/bin/harddrive_model/ and its contents..."
if [ -d /usr/local/bin/harddrive_model ]; then
    rm -rf /usr/local/bin/harddrive_model
    echo "/usr/local/bin/harddrive_model/ removed."
else
    echo "/usr/local/bin/harddrive_model/ not found."
fi

# Remove the application directory
echo "Removing application files..."
rm -rf /opt/SimpleSaferServer

# Remove configuration files
echo "Removing configuration files..."
rm -rf /etc/SimpleSaferServer

# Remove user data
echo "Removing user data..."
rm -rf /var/lib/SimpleSaferServer

# Remove log files
echo "Removing log files..."
rm -rf /var/log/SimpleSaferServer

# Remove Python virtual environment (legacy support)
echo "Removing Python virtual environment..."
rm -rf /opt/SimpleSaferServer/venv

# Remove the user (legacy, safe to keep)
echo "Removing SimpleSaferServer user..."
userdel -r SimpleSaferServer 2>/dev/null

echo "Removing SimpleSaferServer group..."
groupdel SimpleSaferServer 2>/dev/null

# Remove SimpleSaferServer users from Samba
echo "Removing SimpleSaferServer users from Samba..."
# Get list of users from the JSON file if it exists
if [ -f "/etc/SimpleSaferServer/users.json" ]; then
    # Extract usernames from the JSON file and remove them from Samba
    grep -o '"username": "[^"]*"' /etc/SimpleSaferServer/users.json | cut -d'"' -f4 | while read username; do
        echo "Removing Samba user: $username"
        smbpasswd -x "$username" 2>/dev/null || true
    done
fi

# Remove any fstab entries related to SimpleSaferServer
echo "Removing fstab entries..."
# Create a temporary file without the SimpleSaferServer entries
grep -v "SimpleSaferServer" /etc/fstab > /tmp/fstab.new
# Replace the original fstab with the new one
mv /tmp/fstab.new /etc/fstab

# Reload systemd
echo "Reloading systemd..."
systemctl daemon-reload

echo "Uninstallation complete!"
echo "You can now run the install.sh script again to reinstall SimpleSaferServer." 