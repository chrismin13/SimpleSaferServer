#!/bin/bash

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
NC='\033[0m' # No Color

# Welcome banner
clear
echo -e "${BLUE}==============================================="
echo -e "   SimpleSaferServer Installer"
echo -e "===============================================${NC}\n"

# Check for root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}ERROR:${NC} This script must be run as root. Please use sudo or run as root user."
  exit 1
fi

# Determine if we are in a SimpleSaferServer repo
if [ -f "install.sh" ] && [ -d ".git" ] && grep -q 'SimpleSaferServer' README.md 2>/dev/null; then
    SRC_DIR="$(pwd)"
    CLEANUP_CLONE=0
else
    # Ensure git is installed before cloning
    if ! command -v git >/dev/null 2>&1; then
        echo -e "${YELLOW}git is not installed. Installing git...${NC}"
        apt-get update
        apt-get install -y git
        echo -e "${GREEN}✔ git installed.${NC}"
    fi
    echo -e "${YELLOW}Cloning SimpleSaferServer repository...${NC}"
    TMPDIR=$(mktemp -d)
    git clone --depth 1 https://github.com/chrismin13/SimpleSaferServer.git "$TMPDIR/SimpleSaferServer"
    SRC_DIR="$TMPDIR/SimpleSaferServer"
    CLEANUP_CLONE=1
fi

cd "$SRC_DIR"

set -e

APP_DIR="/opt/SimpleSaferServer"
SCRIPTS_DIR="/usr/local/bin"
MODEL_DIR="/opt/SimpleSaferServer/harddrive_model"
SERVICE_FILE="/etc/systemd/system/simple_safer_server_web.service"

# 1. Install system dependencies and Python packages using apt
#    We use apt for Python packages to avoid conflicts with Debian's externally managed Python environment.
#    Do NOT use pip system-wide on Debian/Ubuntu unless absolutely necessary.
echo -e "${YELLOW}Step 1: Installing system and Python dependencies...${NC}"
apt-get update
apt-get install -y python3 python3-pip python3-flask python3-flask-socketio python3-psutil python3-xgboost python3-joblib python3-pandas python3-sklearn python3-cryptography smartmontools samba msmtp

echo -e "${GREEN}✔ System and Python dependencies installed.${NC}\n"

# 2. Install rclone using the official install script
#    The apt version of rclone is missing support for many cloud services (e.g., MEGA, Google Drive, etc).
#    The official script always installs the latest version with all backends.
#    We use 'sudo sh -c' to isolate the install script's exit so it never terminates this script.
echo -e "${YELLOW}Step 2: Installing rclone (latest, all cloud services supported)...${NC}"
sudo -v
TMPFILE=$(mktemp)
curl -s https://rclone.org/install.sh -o "$TMPFILE"
sudo sh -c "bash $TMPFILE || true"
rm -f "$TMPFILE"
echo -e "${GREEN}✔ rclone installed.${NC}\n"

# 3. Copy/update application files (excluding /etc/SimpleSaferServer/)
echo -e "${YELLOW}Step 3: Copying application files...${NC}"
mkdir -p "$APP_DIR"
rsync -a --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' --exclude='*.log' --exclude='telemetry.csv' --exclude='harddrive_model' --exclude='scripts' --exclude='static' --exclude='templates' ./ "$APP_DIR/"
echo -e "${GREEN}✔ Application files copied.${NC}\n"

# 4. Copy static and templates directories
echo -e "${YELLOW}Step 4: Copying static assets and templates...${NC}"
rsync -a static "$APP_DIR/"
rsync -a templates "$APP_DIR/"
echo -e "${GREEN}✔ Static assets and templates copied.${NC}\n"

# 5. Copy scripts to /usr/local/bin and set permissions
echo -e "${YELLOW}Step 5: Installing scripts...${NC}"
mkdir -p "$SCRIPTS_DIR"
for script in scripts/*.sh scripts/*.py; do
  cp "$script" "$SCRIPTS_DIR/"
  chmod +x "$SCRIPTS_DIR/$(basename $script)"
done
echo -e "${GREEN}✔ Scripts installed to $SCRIPTS_DIR.${NC}\n"

# 6. Copy model files
echo -e "${YELLOW}Step 6: Copying model files...${NC}"
mkdir -p "$MODEL_DIR"
cp harddrive_model/* "$MODEL_DIR/"
echo -e "${GREEN}✔ Model files copied.${NC}\n"

# 7. Install/refresh systemd service for Flask app
echo -e "${YELLOW}Step 7: Setting up systemd service...${NC}"
cp simple_safer_server_web.service "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable simple_safer_server_web.service
systemctl restart simple_safer_server_web.service
echo -e "${GREEN}✔ Systemd service enabled and started.${NC}\n"

# 8. Open port 5000 in firewall if active
echo -e "${YELLOW}Step 8: Configuring firewall (if active)...${NC}"
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q 'Status: active'; then
  ufw allow 5000/tcp
echo -e "${GREEN}✔ Port 5000 opened in ufw.${NC}"
elif command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state 2>/dev/null | grep -q running; then
  firewall-cmd --permanent --add-port=5000/tcp
  firewall-cmd --reload
echo -e "${GREEN}✔ Port 5000 opened in firewalld.${NC}"
elif iptables -L | grep -q 'Chain'; then
  iptables -C INPUT -p tcp --dport 5000 -j ACCEPT 2>/dev/null || iptables -A INPUT -p tcp --dport 5000 -j ACCEPT
echo -e "${GREEN}✔ Port 5000 opened in iptables.${NC}"
else
echo -e "${YELLOW}No active firewall detected or configured. Skipping firewall step.${NC}"
fi
echo

# 9. Print all network interface IPs for user access
echo -e "${BLUE}==============================================="
echo -e "  SimpleSaferServer Web UI Access URLs"
echo -e "===============================================${NC}"

# Only show IPv4 addresses, skip 127.0.0.1 and IPv6
IP_LIST=$(hostname -I | tr ' ' '\n' | grep -Eo '([0-9]{1,3}\.){3}[0-9]{1,3}' | grep -v '^127\.')

if [ -z "$IP_LIST" ]; then
  echo -e "${RED}No IPv4 network addresses detected. Please check your network configuration.${NC}"
else
  FIRST_IP=$(echo "$IP_LIST" | head -n 1)
  echo -e "${GREEN}Recommended:${NC} http://$FIRST_IP:5000"
  for ip in $IP_LIST; do
    if [ "$ip" != "$FIRST_IP" ]; then
      echo "  http://$ip:5000"
    fi
  done
fi
echo

echo -e "${GREEN}✔ Installation/update complete!${NC}"
echo -e "${YELLOW}If this is your first install, visit the above address in your browser to complete setup via the web UI.${NC}"
echo -e "${BLUE}===============================================${NC}\n"

# At the end, clean up if we cloned
if [ "$CLEANUP_CLONE" = "1" ]; then
    echo -e "${YELLOW}Cleaning up temporary files...${NC}"
    rm -rf "$TMPDIR"
fi 
