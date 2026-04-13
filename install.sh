#!/bin/bash

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
NC='\033[0m' # No Color

# Welcome banner
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
SCRIPTS_DIR="$APP_DIR/scripts"
BIN_DIR="/usr/local/bin"
MODEL_DIR="/opt/SimpleSaferServer/harddrive_model"
VENV_DIR="$APP_DIR/venv"
SERVICE_FILE="/etc/systemd/system/simple_safer_server_web.service"
HDSENTINEL_BIN="/usr/local/bin/hdsentinel"
HDSENTINEL_ASSET_DIR="$SRC_DIR/third_party/hdsentinel"

detect_hdsentinel_arch() {
    local arch=""
    local machine=""

    if command -v dpkg >/dev/null 2>&1; then
        arch=$(dpkg --print-architecture 2>/dev/null || true)
    fi

    # Prefer Debian's package architecture when it is available because that
    # reflects the userspace ABI we need to run, not just the kernel's CPU view.
    if [ -n "$arch" ]; then
        printf '%s\n' "$arch"
        return 0
    fi

    machine=$(uname -m 2>/dev/null || true)
    machine=${machine,,}

    case "$machine" in
        x86_64*|amd64*)
            printf '%s\n' "amd64"
            ;;
        aarch64*|arm64*)
            printf '%s\n' "arm64"
            ;;
        armv7*|armv8l*|armhf*)
            # The vendored 32-bit ARM build is the ARMv7 hard-float variant.
            # Matching armv8l here is intentional because it is commonly a
            # 32-bit userspace on newer ARM hardware.
            printf '%s\n' "armhf"
            ;;
        *)
            printf '%s\n' "$machine"
            ;;
    esac
}

install_hdsentinel() {
    local arch=""
    local asset_path=""
    local package_path=""
    local tmpdir=""
    local candidate=""

    arch=$(detect_hdsentinel_arch)

    case "$arch" in
        amd64)
            asset_path="$HDSENTINEL_ASSET_DIR/hdsentinel-linux-amd64.zip"
            ;;
        arm64)
            asset_path="$HDSENTINEL_ASSET_DIR/hdsentinel-linux-arm64.zip"
            ;;
        armhf)
            # This asset is repackaged from the vendor's ARMv7 release, so we
            # deliberately do not pretend older ARM variants are compatible.
            asset_path="$HDSENTINEL_ASSET_DIR/hdsentinel-linux-armv7.zip"
            ;;
        *)
            echo -e "${YELLOW}HDSentinel auto-install skipped: unsupported architecture '${arch:-unknown}'.${NC}"
            return 0
            ;;
    esac

    tmpdir=$(mktemp -d)
    # The automated installer only trusts vendored HDSentinel archives so the
    # binary source stays pinned to files shipped with this repo.
    if [ ! -f "$asset_path" ]; then
        echo -e "${YELLOW}Bundled HDSentinel package not found for ${arch}. Skipping HDSentinel auto-install.${NC}"
        rm -rf "$tmpdir"
        return 0
    fi

    package_path="$tmpdir/$(basename "$asset_path")"
    cp "$asset_path" "$package_path"
    echo -e "${GREEN}✔ Using bundled HDSentinel package: $asset_path${NC}"

    if ! unzip -o "$package_path" -d "$tmpdir" >/dev/null; then
        echo -e "${YELLOW}HDSentinel extraction failed. Continuing without it.${NC}"
        rm -rf "$tmpdir"
        return 0
    fi

    for extracted in "$tmpdir"/HDSentinel*; do
        if [ -f "$extracted" ]; then
            candidate="$extracted"
            break
        fi
    done

    if [ -z "$candidate" ]; then
        echo -e "${YELLOW}HDSentinel binary not found in downloaded archive. Continuing without it.${NC}"
        rm -rf "$tmpdir"
        return 0
    fi

    install -m 755 "$candidate" "$HDSENTINEL_BIN"
    rm -rf "$tmpdir"
    echo -e "${GREEN}✔ HDSentinel installed to $HDSENTINEL_BIN.${NC}\n"
}

# 1. Install system dependencies and the base Python runtime using apt.
#    The app itself runs from a dedicated virtualenv so older Debian releases
#    are not blocked by missing distro packages like python3-flask-socketio.
echo -e "${YELLOW}Step 1: Installing system and Python dependencies...${NC}"
apt-get update
# Preseed AppArmor prompt for msmtp only to ensure non-interactive install
echo "msmtp msmtp/apply_apparmor boolean true" | debconf-set-selections
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-pip python3-venv python3-flask python3-psutil python3-cryptography smartmontools samba msmtp curl unzip rsync ntfs-3g

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

# 3. Install HDSentinel for supported architectures
echo -e "${YELLOW}Step 3: Installing HDSentinel...${NC}"
install_hdsentinel

# 4. Copy/update application files (excluding /etc/SimpleSaferServer/)
echo -e "${YELLOW}Step 4: Copying application files...${NC}"
mkdir -p "$APP_DIR"
rsync -a --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' --exclude='*.log' --exclude='telemetry.csv' --exclude='harddrive_model' --exclude='static' --exclude='templates' ./ "$APP_DIR/"
echo -e "${GREEN}✔ Application files copied.${NC}\n"

# 5. Copy static and templates directories
echo -e "${YELLOW}Step 5: Copying static assets and templates...${NC}"
rsync -a static "$APP_DIR/"
rsync -a templates "$APP_DIR/"
echo -e "${GREEN}✔ Static assets and templates copied.${NC}\n"

# 6. Create the dedicated app virtualenv and install Python packages.
echo -e "${YELLOW}Step 6: Setting up Python virtualenv...${NC}"
python3 -m venv --system-site-packages "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip wheel
"$VENV_DIR/bin/pip" install "Flask-SocketIO==5.4.1"
if ! "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements-ml.txt"; then
  echo -e "${YELLOW}ML package installation failed. Continuing without the optional SMART prediction stack.${NC}"
fi
echo -e "${GREEN}✔ Python virtualenv ready at $VENV_DIR.${NC}\n"

# 7. Copy scripts to /opt/SimpleSaferServer/scripts and /usr/local/bin
echo -e "${YELLOW}Step 7: Installing scripts...${NC}"
mkdir -p "$SCRIPTS_DIR"
mkdir -p "$BIN_DIR"
for script in scripts/*.sh scripts/*.py; do
  cp "$script" "$SCRIPTS_DIR/"
  chmod +x "$SCRIPTS_DIR/$(basename $script)"
  cp "$script" "$BIN_DIR/"
  chmod +x "$BIN_DIR/$(basename $script)"
done
echo -e "${GREEN}✔ Scripts installed to $SCRIPTS_DIR and $BIN_DIR.${NC}\n"

# 8. Copy model files
echo -e "${YELLOW}Step 8: Copying model files...${NC}"
mkdir -p "$MODEL_DIR"
cp harddrive_model/* "$MODEL_DIR/"
echo -e "${GREEN}✔ Model files copied.${NC}\n"

# 9. Install/refresh systemd service for Flask app
echo -e "${YELLOW}Step 9: Setting up systemd service...${NC}"
cp simple_safer_server_web.service "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable simple_safer_server_web.service
systemctl restart simple_safer_server_web.service
echo -e "${GREEN}✔ Systemd service enabled and started.${NC}\n"

# 10. Refresh procedurally generated background services
echo -e "${YELLOW}Step 10: Refreshing procedural background services...${NC}"
if "$VENV_DIR/bin/python3" -c "
import sys
sys.path.insert(0, '$APP_DIR')
from config_manager import ConfigManager
from runtime import get_runtime
from system_utils import SystemUtils

rt = get_runtime()
config = ConfigManager(runtime=rt).get_all_config()
# install_systemd_services_and_timers catches exceptions and returns (success, error)
# rather than raising, so we must check the tuple explicitly.
success, error = SystemUtils(runtime=rt).install_systemd_services_and_timers(config)
if not success:
    print(f'Error: {error}', file=sys.stderr)
    sys.exit(1)
"; then
  echo -e "${GREEN}✔ Background services generated and restarted.${NC}\n"
else
  echo -e "${RED}ERROR: Failed to generate and register background services.${NC}"
  echo -e "${RED}DDNS and other scheduled tasks will not run without the systemd units.${NC}"
  echo -e "${YELLOW}Remediation:${NC}"
  echo -e "  1. Check the error message printed above for details."
  echo -e "  2. Review systemd logs with: journalctl -xe"
  echo -e "  3. Fix the reported issue and rerun this installer."
  exit 1
fi

# 11. Open port 5000 in firewall if active
echo -e "${YELLOW}Step 11: Configuring firewall (if active)...${NC}"
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

# 12. Print all network interface IPs for user access
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
