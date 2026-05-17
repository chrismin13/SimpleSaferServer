#!/bin/bash

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
NC='\033[0m' # No Color

# Welcome banner
echo -e "${BLUE}===============================================${NC}"
echo -e "${BLUE}   SimpleSaferServer Installer${NC}"
echo -e "${BLUE}===============================================${NC}\n"

UNSUPPORTED_OS_OK="${SSS_UNSUPPORTED_OS_OK:-0}"
PREFLIGHT_ONLY="${SSS_INSTALLER_PREFLIGHT_ONLY:-0}"
OS_RELEASE_PATH="${SSS_OS_RELEASE_PATH:-}"

while [ "$#" -gt 0 ]; do
    case "$1" in
        --unsupported-os-ok)
            UNSUPPORTED_OS_OK=1
            ;;
        *)
            echo -e "${RED}ERROR:${NC} Unknown installer option: $1"
            exit 1
            ;;
    esac
    shift
done

installer_command_available() {
    local command_name="$1"
    local fake_commands=",${SSS_INSTALLER_TEST_COMMANDS:-},"
    local missing_commands=",${SSS_INSTALLER_TEST_MISSING_COMMANDS:-},"

    if [ "$PREFLIGHT_ONLY" = "1" ] && [ "${fake_commands}" != ",," ]; then
        case "$fake_commands" in
            *,"$command_name",*) return 0 ;;
        esac
        return 1
    fi

    if [ "$PREFLIGHT_ONLY" = "1" ] && [ "${missing_commands}" != ",," ]; then
        case "$missing_commands" in
            *,"$command_name",*) return 1 ;;
        esac
    fi

    command -v "$command_name" >/dev/null 2>&1
}

installer_systemd_available() {
    if [ "$PREFLIGHT_ONLY" = "1" ] && [ "${SSS_INSTALLER_TEST_SYSTEMD:-0}" = "1" ]; then
        return 0
    fi
    # Normal Debian/Ubuntu server installs are systemd-booted. This catches
    # chroots and minimal containers where systemctl exists but service setup
    # would fail later with a much less useful error.
    [ -d /run/systemd/system ]
}

os_release_file() {
    if [ -n "$OS_RELEASE_PATH" ]; then
        printf '%s\n' "$OS_RELEASE_PATH"
        return 0
    fi
    if [ -r /etc/os-release ]; then
        printf '%s\n' /etc/os-release
        return 0
    fi
    if [ -r /usr/lib/os-release ]; then
        printf '%s\n' /usr/lib/os-release
        return 0
    fi
    return 1
}

os_release_value() {
    local file="$1"
    local key="$2"
    local line=""
    line=$(grep -E "^[[:space:]]*${key}=" "$file" 2>/dev/null | tail -n 1 || true)
    line=${line#"${line%%[![:space:]]*}"}
    line=${line#*=}
    line=${line%\"}
    line=${line#\"}
    line=${line%\'}
    line=${line#\'}
    printf '%s\n' "$line"
}

contains_os_family() {
    local value=" $1 "
    local family="$2"
    case "$value" in
        *" $family "*) return 0 ;;
    esac
    return 1
}

same_file() {
    local source_path="$1"
    local dest_path="$2"
    local source_real=""
    local dest_real=""

    source_real="$(readlink -f "$source_path")"
    dest_real="$(readlink -f "$dest_path" 2>/dev/null || printf '%s' "$dest_path")"
    [ "$source_real" = "$dest_real" ]
}

copy_unless_same_file() {
    local source_path="$1"
    local dest_path="$2"

    if same_file "$source_path" "$dest_path"; then
        return 0
    fi
    cp "$source_path" "$dest_path"
}

ensure_git_safe_directory() {
    local repo_path="$1"
    local existing_paths=""

    if ! command -v git >/dev/null 2>&1; then
        return 0
    fi

    existing_paths="$(git config --system --get-all safe.directory 2>/dev/null || true)"
    if printf '%s\n' "$existing_paths" | grep -Fxq "$repo_path"; then
        return 0
    fi

    # The app checkout may be owned by the installing admin while update services
    # run as root without sudo's SUDO_UID trust hint, so root Git commands need an
    # explicit safe.directory entry for the managed app folder.
    git config --system --add safe.directory "$repo_path"
}

run_installer_preflight() {
    local release_file=""
    local os_id=""
    local os_like=""
    local pretty_name=""
    local version_id=""
    local missing_tools=""
    local is_debian_family=0
    local is_direct_supported_family=0

    echo -e "${YELLOW}Preflight: Checking install platform...${NC}"

    if ! installer_command_available apt-get; then
        missing_tools="${missing_tools} apt-get"
    fi
    if ! installer_command_available dpkg; then
        missing_tools="${missing_tools} dpkg"
    fi
    if ! installer_command_available systemctl; then
        missing_tools="${missing_tools} systemctl"
    fi

    if [ -n "$missing_tools" ]; then
        echo -e "${RED}ERROR:${NC} Missing required host tools:${missing_tools}"
        echo -e "SimpleSaferServer installs Debian packages and systemd services, so this installer needs apt-get, dpkg, and systemctl."
        exit 1
    fi
    if ! installer_systemd_available; then
        echo -e "${RED}ERROR:${NC} systemctl is installed, but systemd does not appear to be running as the host init system."
        echo -e "This usually means the installer is running inside a chroot, build container, or other non-booted environment. Run it on the target Debian/Ubuntu server instead."
        exit 1
    fi

    if release_file=$(os_release_file); then
        os_id=$(os_release_value "$release_file" ID | tr '[:upper:]' '[:lower:]')
        os_like=$(os_release_value "$release_file" ID_LIKE | tr '[:upper:]' '[:lower:]')
        pretty_name=$(os_release_value "$release_file" PRETTY_NAME)
        version_id=$(os_release_value "$release_file" VERSION_ID)
    else
        echo -e "${YELLOW}Could not read /etc/os-release or /usr/lib/os-release.${NC}"
        echo -e "${YELLOW}Continuing because the required Debian package and systemd tools are present.${NC}"
        echo
        return 0
    fi

    case "$os_id" in
        debian|ubuntu)
            is_debian_family=1
            is_direct_supported_family=1
            ;;
        *)
            if contains_os_family "$os_like" debian || contains_os_family "$os_like" ubuntu; then
                is_debian_family=1
            fi
            ;;
    esac

    if [ "$is_debian_family" -ne 1 ]; then
        if [ "$UNSUPPORTED_OS_OK" = "1" ]; then
            echo -e "${YELLOW}Unsupported OS family detected (${pretty_name:-$os_id}); continuing because --unsupported-os-ok was set.${NC}"
        else
            echo -e "${RED}ERROR:${NC} Unsupported OS family detected: ${pretty_name:-$os_id}"
            echo -e "SimpleSaferServer expects a Debian/Ubuntu-style APT and systemd host."
            echo -e "Use --unsupported-os-ok only if this system intentionally provides compatible APT and systemd behavior."
            exit 1
        fi
    elif [ "$is_direct_supported_family" -eq 1 ]; then
        echo -e "${GREEN}✔ Detected ${pretty_name:-$os_id $version_id}.${NC}"
        case "$os_id:$version_id" in
            debian:10*|ubuntu:20.04*)
                echo -e "${YELLOW}This is a legacy compatibility platform. The installer will use older Python dependencies if the installed Python runtime requires them.${NC}"
                ;;
        esac
    else
        echo -e "${YELLOW}Detected Debian/Ubuntu-family derivative: ${pretty_name:-$os_id $version_id}.${NC}"
        echo -e "${YELLOW}Continuing because APT and systemd are available; derivative package differences may still cause apt-get to fail later.${NC}"
    fi

    echo -e "${GREEN}✔ Install platform preflight passed.${NC}\n"
}

# Check for root
if [ "$EUID" -ne 0 ] && [ "$PREFLIGHT_ONLY" != "1" ]; then
  echo -e "${RED}ERROR:${NC} This script must be run as root. Please use sudo or run as root user."
  exit 1
fi

run_installer_preflight
if [ "$PREFLIGHT_ONLY" = "1" ]; then
    exit 0
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
DATA_DIR="/var/lib/SimpleSaferServer"
SCRIPTS_DIR="$APP_DIR/scripts"
BIN_DIR="/usr/local/bin"
MODEL_DIR="/opt/SimpleSaferServer/harddrive_model"
VENV_DIR="$APP_DIR/venv"
SERVICE_FILE="/etc/systemd/system/simple_safer_server_web.service"
HDSENTINEL_BIN="/usr/local/bin/hdsentinel"
HDSENTINEL_ASSET_DIR="$SRC_DIR/third_party/hdsentinel"
REQUIREMENTS_FILE="requirements.txt"
PIP_UPGRADE_SPEC=(pip wheel)

python_runtime_version() {
    python3 - <<'PY'
import sys

print("{}.{}".format(sys.version_info.major, sys.version_info.minor))
PY
}

python_requires_legacy_requirements() {
    python3 - <<'PY'
import sys

# Flask 3.1 and several audited dependency fixes require Python 3.9+.
# Choose by interpreter version so Ubuntu 20.04/Python 3.8 and similar
# platforms do not attempt to install the modern security baseline.
raise SystemExit(0 if sys.version_info < (3, 9) else 1)
PY
}

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

install_optional_wsdd2() {
    echo -e "${YELLOW}Installing optional wsdd2 discovery support...${NC}"
    if DEBIAN_FRONTEND=noninteractive apt-get install -y wsdd2; then
        echo -e "${GREEN}✔ wsdd2 installed for modern Windows Network discovery.${NC}\n"
    else
        # wsdd2 is absent on some supported Debian-family releases. Samba file
        # serving must still install cleanly when only discovery is degraded.
        echo -e "${YELLOW}wsdd2 is unavailable or could not be installed. Continuing without modern Windows discovery.${NC}\n"
    fi
}

configure_samba_discovery_services() {
    local smbd_state=""
    local nmbd_state=""
    local wsdd2_state=""
    local smbd_enable_failed=0
    local smbd_start_failed=0
    local nmbd_enable_failed=0
    local nmbd_start_failed=0
    local wsdd2_enable_failed=0
    local wsdd2_start_failed=0

    echo -e "${YELLOW}Configuring Samba file sharing and discovery services...${NC}"

    # smbd is the required file-serving daemon. Enable/start failures are not
    # fatal by themselves because a unit can still be active after a manual
    # start or distro-specific boot policy; the final active state is the gate.
    if ! systemctl enable smbd; then
        smbd_enable_failed=1
    fi
    if ! systemctl start smbd; then
        smbd_start_failed=1
    fi
    if ! systemctl is-active --quiet smbd; then
        echo -e "${RED}ERROR: smbd is not active after start.${NC}"
        echo -e "${RED}Samba file serving is required, so installation cannot continue safely.${NC}"
        echo -e "${RED}Run 'systemctl status smbd' and 'journalctl -u smbd --no-pager' to inspect the failure, then rerun the installer after smbd can start.${NC}"
        return 1
    fi
    if [ "$smbd_enable_failed" -eq 1 ]; then
        echo -e "${YELLOW}WARNING: smbd is active, but systemctl enable smbd failed. File sharing works now, but it may not survive reboot until boot enablement is fixed.${NC}"
    fi
    if [ "$smbd_start_failed" -eq 1 ]; then
        echo -e "${YELLOW}WARNING: smbd is active, but systemctl start smbd failed. File sharing works now, but review the service state before relying on it.${NC}"
    fi

    if ! systemctl enable nmbd; then
        nmbd_enable_failed=1
    fi
    if ! systemctl start nmbd; then
        nmbd_start_failed=1
    fi
    if [ "$nmbd_enable_failed" -eq 1 ] || [ "$nmbd_start_failed" -eq 1 ]; then
        echo -e "${YELLOW}nmbd could not be enabled or started. Continuing with legacy NetBIOS discovery degraded.${NC}"
    fi
    if ! systemctl is-active --quiet nmbd; then
        echo -e "${YELLOW}nmbd is not active. Legacy NetBIOS discovery may be unavailable.${NC}"
    fi

    # Try the packaged unit directly. Missing wsdd2 units are non-fatal because
    # wsdd2 is optional and package availability varies by distro release.
    if ! systemctl enable wsdd2; then
        wsdd2_enable_failed=1
    fi
    if ! systemctl start wsdd2; then
        wsdd2_start_failed=1
    fi
    if [ "$wsdd2_enable_failed" -eq 1 ] || [ "$wsdd2_start_failed" -eq 1 ]; then
        echo -e "${YELLOW}wsdd2 could not be enabled or started. Continuing with modern Windows discovery degraded.${NC}"
    fi
    if ! systemctl is-active --quiet wsdd2; then
        echo -e "${YELLOW}wsdd2 is not active or unavailable. Modern Windows Network discovery may be unavailable.${NC}"
    fi

    if systemctl is-active --quiet smbd; then
        smbd_state="active"
    else
        smbd_state="inactive"
    fi
    if systemctl is-active --quiet nmbd; then
        nmbd_state="active"
    else
        nmbd_state="inactive"
    fi
    if systemctl is-active --quiet wsdd2; then
        wsdd2_state="active"
    elif systemctl cat wsdd2 >/dev/null 2>&1; then
        wsdd2_state="inactive"
    else
        wsdd2_state="unavailable"
    fi

    echo -e "${BLUE}Samba service summary:${NC}"
    echo -e "  smbd: ${smbd_state}"
    echo -e "  nmbd: ${nmbd_state}"
    echo -e "  wsdd2: ${wsdd2_state}"
    echo -e "${GREEN}✔ Samba service setup complete.${NC}\n"
}

# 1. Install system dependencies and the base Python runtime using apt.
#    The app itself runs from a dedicated virtualenv so older Debian releases
#    are not blocked by missing distro packages like python3-flask-socketio.
echo -e "${YELLOW}Step 1: Installing system and Python dependencies...${NC}"
apt-get update
# Preseed AppArmor prompt for msmtp only to ensure non-interactive install
echo "msmtp msmtp/apply_apparmor boolean true" | debconf-set-selections
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-pip python3-venv python3-flask python3-psutil python3-cryptography smartmontools samba msmtp curl unzip rsync fdisk ntfs-3g unattended-upgrades

echo -e "${GREEN}✔ System and Python dependencies installed.${NC}\n"
install_optional_wsdd2

PYTHON_RUNTIME_VERSION="$(python_runtime_version)"
if python_requires_legacy_requirements; then
    REQUIREMENTS_FILE="requirements-legacy-py37.txt"
    PIP_UPGRADE_SPEC=("pip<24.1" wheel)
    echo -e "${YELLOW}Python ${PYTHON_RUNTIME_VERSION} detected. Installing the legacy Python dependency set for runtimes older than 3.9.${NC}"
    echo -e "${YELLOW}Security fixes for some Python packages require newer Python releases; use Debian 13+ or another Python 3.9+ platform for the strict security-supported baseline.${NC}\n"
fi

# 2. Install rclone using the official install script
#    The apt version of rclone is missing support for many cloud services (e.g., MEGA, Google Drive, etc).
#    The official script always installs the latest version with all backends.
#    This installer already runs as root, so avoid depending on sudo being present
#    on minimal Debian servers.
echo -e "${YELLOW}Step 2: Installing rclone (latest, all cloud services supported)...${NC}"
TMPFILE=$(mktemp)
# Cloud backup is part of the supported setup path, so a missing rclone should
# stop installation instead of producing a partially capable server.
if curl -fS https://rclone.org/install.sh -o "$TMPFILE"; then
  if bash "$TMPFILE"; then
    echo -e "${GREEN}✔ rclone installed.${NC}\n"
  else
    RCLONE_INSTALL_EXIT_CODE=$?
    # The upstream script returns 3 when the newest rclone is already present.
    # Verify the binary before deciding whether this server is actually unsafe.
    if command -v rclone >/dev/null 2>&1; then
      echo -e "${YELLOW}rclone installer exited with code ${RCLONE_INSTALL_EXIT_CODE}, but rclone is available.${NC}"
      rclone version | head -n 1
      echo -e "${GREEN}✔ rclone is installed.${NC}\n"
    else
      echo -e "${RED}ERROR: Failed to install rclone. Exit code: ${RCLONE_INSTALL_EXIT_CODE}.${NC}"
      echo -e "${RED}Cloud backup requires rclone, so SimpleSaferServer cannot complete installation safely.${NC}"
      echo -e "${YELLOW}Remediation:${NC}"
      echo -e "  1. Check network access to https://rclone.org/install.sh"
      echo -e "  2. Install rclone manually if needed: https://rclone.org/install/"
      echo -e "  3. Rerun this installer."
      rm -f "$TMPFILE"
      exit 1
    fi
  fi
else
  RCLONE_DOWNLOAD_EXIT_CODE=$?
  echo -e "${RED}ERROR: Failed to download rclone installer. Exit code: ${RCLONE_DOWNLOAD_EXIT_CODE}.${NC}"
  echo -e "${RED}Cloud backup requires rclone, so SimpleSaferServer cannot complete installation safely.${NC}"
  echo -e "${YELLOW}Remediation:${NC}"
  echo -e "  1. Check network access to https://rclone.org/install.sh"
  echo -e "  2. Install rclone manually if needed: https://rclone.org/install/"
  echo -e "  3. Rerun this installer."
  rm -f "$TMPFILE"
  exit 1
fi
rm -f "$TMPFILE"

# 3. Install HDSentinel for supported architectures
echo -e "${YELLOW}Step 3: Installing HDSentinel...${NC}"
install_hdsentinel

# 4. Copy/update application files (excluding app-owned subtrees handled below)
echo -e "${YELLOW}Step 4: Copying application files...${NC}"
mkdir -p "$APP_DIR"
mkdir -p "$DATA_DIR"
rsync -a --delete --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' --exclude='*.log' --exclude='telemetry.csv' --exclude='harddrive_model' --exclude='/static' --exclude='/templates' ./ "$APP_DIR/"
echo -e "${GREEN}✔ Application files copied.${NC}\n"

# 5. Copy static and templates directories
echo -e "${YELLOW}Step 5: Copying static assets and templates...${NC}"
rsync -a --delete static "$APP_DIR/"
rsync -a --delete templates "$APP_DIR/"
echo -e "${GREEN}✔ Static assets and templates copied.${NC}\n"

# 6. Create the dedicated app virtualenv and install Python packages.
echo -e "${YELLOW}Step 6: Setting up Python virtualenv...${NC}"
python3 -m venv --system-site-packages "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade "${PIP_UPGRADE_SPEC[@]}"
"$VENV_DIR/bin/pip" install -r "$REQUIREMENTS_FILE"
echo -e "${GREEN}✔ Python virtualenv ready at $VENV_DIR.${NC}\n"

# 7. Copy scripts to /opt/SimpleSaferServer/scripts and /usr/local/bin
echo -e "${YELLOW}Step 7: Installing scripts...${NC}"
mkdir -p "$SCRIPTS_DIR"
mkdir -p "$BIN_DIR"
for script in scripts/*.sh scripts/*.py; do
  script_name="$(basename "$script")"
  app_script_path="$SCRIPTS_DIR/$script_name"
  bin_script_path="$BIN_DIR/$script_name"
  # Reinstalling from /opt/SimpleSaferServer makes the app script source and
  # destination the same file. Skip copy and chmod there so the installer does
  # not dirty the Git checkout that future self-updates need to inspect.
  if ! same_file "$script" "$app_script_path"; then
    cp "$script" "$app_script_path"
  fi
  copy_unless_same_file "$script" "$bin_script_path"
  chmod +x "$bin_script_path"
done
echo -e "${GREEN}✔ Scripts installed to $SCRIPTS_DIR and $BIN_DIR.${NC}\n"

# Root-run systemd services do not inherit sudo's repository-owner trust context.
ensure_git_safe_directory "$APP_DIR"

# 8. Copy model files
echo -e "${YELLOW}Step 8: Copying model files...${NC}"
mkdir -p "$MODEL_DIR"
# Model files are bundled application artifacts. Pruning here keeps removed
# model artifacts from lingering after installs from a separate checkout.
if ! same_file harddrive_model "$MODEL_DIR"; then
  rsync -a --delete harddrive_model/ "$MODEL_DIR/"
fi
echo -e "${GREEN}✔ Model files copied.${NC}\n"

# 9. Prepare the SSS-owned Samba include layout and discovery services.
echo -e "${YELLOW}Step 9: Preparing Samba file sharing and discovery...${NC}"
if "$VENV_DIR/bin/python3" -c "
import sys
sys.path.insert(0, '$APP_DIR')
from simple_safer_server.services.runtime import get_runtime
from simple_safer_server.services.samba_layout import SambaLayoutService

rt = get_runtime()
SambaLayoutService(runtime=rt).ensure_layout()
"; then
  echo -e "${GREEN}✔ Samba include layout prepared.${NC}"
else
  echo -e "${RED}ERROR: Failed to prepare the SimpleSaferServer Samba include layout.${NC}"
  echo -e "${RED}Samba must validate before installation can continue safely.${NC}"
  exit 1
fi
if configure_samba_discovery_services; then
  echo -e "${GREEN}✔ Required Samba file serving is active.${NC}"
else
  echo -e "${RED}ERROR: Failed to start required Samba file serving.${NC}"
  echo -e "${RED}Fix smbd with 'systemctl status smbd' and 'journalctl -u smbd --no-pager', then rerun the installer.${NC}"
  exit 1
fi

# 10. Install/refresh systemd service for Flask app
echo -e "${YELLOW}Step 10: Setting up systemd service...${NC}"
cp simple_safer_server_web.service "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable simple_safer_server_web.service
systemctl restart simple_safer_server_web.service
echo -e "${GREEN}✔ Systemd service enabled and started.${NC}\n"

# 11. Refresh procedurally generated background services
echo -e "${YELLOW}Step 11: Refreshing procedural background services...${NC}"
if "$VENV_DIR/bin/python3" -c "
import sys
sys.path.insert(0, '$APP_DIR')
from simple_safer_server.services.config_manager import ConfigManager
from simple_safer_server.services.runtime import get_runtime
from simple_safer_server.services.system_utils import SystemUtils

rt = get_runtime()
config = ConfigManager(runtime=rt).get_all_config()
setup_complete_raw = config.get('system', {}).get('setup_complete', 'false')
setup_complete = setup_complete_raw is True or str(setup_complete_raw).lower() == 'true'
# install_systemd_services_and_timers catches exceptions and returns (success, error)
# rather than raising, so we must check the tuple explicitly.
success, error = SystemUtils(runtime=rt).install_systemd_services_and_timers(
    config,
    activate_timers=setup_complete,
)
if not success:
    print(f'Error: {error}', file=sys.stderr)
    sys.exit(1)
"; then
  echo -e "${GREEN}✔ Background services generated. Recurring timers are active only after setup is complete.${NC}\n"
else
  echo -e "${RED}ERROR: Failed to generate and register background services.${NC}"
  echo -e "${RED}DDNS and other scheduled tasks will not run without the systemd units.${NC}"
  echo -e "${YELLOW}Remediation:${NC}"
  echo -e "  1. Check the error message printed above for details."
  echo -e "  2. Review systemd logs with: journalctl -xe"
  echo -e "  3. Fix the reported issue and rerun this installer."
  exit 1
fi

# 12. Open port 5000 in firewall if active
echo -e "${YELLOW}Step 12: Configuring firewall (if active)...${NC}"
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

# 13. Print all network interface IPs for user access
echo -e "${BLUE}===============================================${NC}"
echo -e "${BLUE}  SimpleSaferServer Web UI Access URLs${NC}"
echo -e "${BLUE}===============================================${NC}"

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
