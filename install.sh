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
SOURCE_ARCHIVE_URL="${SSS_SOURCE_ARCHIVE_URL:-https://github.com/chrismin13/SimpleSaferServer/archive/refs/heads/main.tar.gz}"

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
  if [ "$PREFLIGHT_ONLY" = "1" ] && [ -n "${SSS_INSTALLER_TEST_SYSTEMD+x}" ]; then
    [ "$SSS_INSTALLER_TEST_SYSTEMD" = "1" ]
    return
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

installer_architecture() {
  if [ "$PREFLIGHT_ONLY" = "1" ] && [ -n "${SSS_INSTALLER_TEST_ARCH:-}" ]; then
    printf '%s\n' "$SSS_INSTALLER_TEST_ARCH"
    return 0
  fi
  dpkg --print-architecture 2>/dev/null || uname -m
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

run_installer_preflight() {
  local release_file=""
  local os_id=""
  local os_like=""
  local pretty_name=""
  local version_id=""
  local missing_tools=""
  local is_debian_family=0
  local is_direct_supported_family=0
  local host_arch=""

  echo -e "${YELLOW}Preflight: Checking install platform...${NC}"

  if ! installer_command_available systemctl; then
    missing_tools="${missing_tools} systemctl"
  fi
  if ! installer_command_available curl; then
    missing_tools="${missing_tools} curl"
  fi
  if ! installer_command_available sudo; then
    missing_tools="${missing_tools} sudo"
  fi

  if [ -n "$missing_tools" ]; then
    echo -e "${RED}ERROR:${NC} Missing required host tools:${missing_tools}"
    echo -e "SimpleSaferServer downloads release archives, configures systemd services, and runs its services as a dedicated user, so this installer needs curl, systemctl, and sudo."
    exit 1
  fi
  if ! installer_systemd_available; then
    echo -e "${RED}ERROR:${NC} systemctl is installed, but systemd does not appear to be running as the host init system."
    echo -e "This usually means the installer is running inside a chroot, build container, or other non-booted environment. Run it on the target Debian/Ubuntu server instead."
    exit 1
  fi

  host_arch=$(installer_architecture)
  case "$host_arch" in
    amd64 | x86_64 | arm64 | aarch64)
      ;;
    *)
      echo -e "${RED}ERROR:${NC} Unsupported architecture detected: ${host_arch:-unknown}."
      echo -e "SimpleSaferServer requires a 64-bit OS/userspace for uv-managed Python and binary Python dependencies. Use amd64 or arm64."
      exit 1
      ;;
  esac

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
    debian | ubuntu)
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
      echo -e "SimpleSaferServer expects a Debian/Ubuntu-style systemd host."
      echo -e "Use --unsupported-os-ok only if this system intentionally provides compatible systemd behavior."
      exit 1
    fi
  elif [ "$is_direct_supported_family" -eq 1 ]; then
    echo -e "${GREEN}✔ Detected ${pretty_name:-$os_id $version_id}.${NC}"
  else
    echo -e "${YELLOW}Detected Debian/Ubuntu-family derivative: ${pretty_name:-$os_id $version_id}.${NC}"
    echo -e "${YELLOW}Continuing because the base installer only needs the app archive, uv, and systemd services.${NC}"
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

# Determine if we are already running from a SimpleSaferServer source tree.
if [ -f "install.sh" ] && [ -d "simple_safer_server" ] && [ -f "pyproject.toml" ]; then
  SRC_DIR="$(pwd)"
  CLEANUP_SOURCE=0
else
  echo -e "${YELLOW}Downloading SimpleSaferServer source archive...${NC}"
  TMPDIR=$(mktemp -d)
  TMPFILE=$(mktemp)
  if ! curl -fLsS "$SOURCE_ARCHIVE_URL" -o "$TMPFILE"; then
    rm -f "$TMPFILE"
    rm -rf "$TMPDIR"
    echo -e "${RED}ERROR: Failed to download SimpleSaferServer source archive.${NC}"
    exit 1
  fi
  if ! tar -xzf "$TMPFILE" -C "$TMPDIR"; then
    rm -f "$TMPFILE"
    rm -rf "$TMPDIR"
    echo -e "${RED}ERROR: Failed to extract SimpleSaferServer source archive.${NC}"
    exit 1
  fi
  rm -f "$TMPFILE"
  SRC_DIR="$(find "$TMPDIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
  if [ -z "$SRC_DIR" ] || [ ! -f "$SRC_DIR/install.sh" ] || [ ! -d "$SRC_DIR/simple_safer_server" ]; then
    rm -rf "$TMPDIR"
    echo -e "${RED}ERROR: Downloaded archive did not contain a SimpleSaferServer source tree.${NC}"
    exit 1
  fi
  CLEANUP_SOURCE=1
fi

cd "$SRC_DIR"

set -e

APP_DIR="/opt/SimpleSaferServer"
DATA_DIR="/var/lib/SimpleSaferServer"
CONFIG_DIR="/etc/SimpleSaferServer"
LOG_DIR="/var/log/SimpleSaferServer"
VOLATILE_DIR="/run/SimpleSaferServer"
BIN_DIR="/usr/local/bin"
VENV_DIR="$APP_DIR/.venv"
APP_USER="sss"
APP_GROUP="sss"
SERVICE_USER_MARKER="$DATA_DIR/.sss-user-created"
SERVICE_GROUP_MARKER="$DATA_DIR/.sss-group-created"
MIN_UV_VERSION="0.11.13"
UV_INSTALL_DIR="/usr/local/bin"
UV_INSTALL_URL="https://astral.sh/uv/install.sh"
SERVICE_FILE="/etc/systemd/system/simple-safer-server-web.service"
WORKER_SERVICE_FILE="/etc/systemd/system/simple-safer-server-worker.service"
SUDOERS_FILE="/etc/sudoers.d/simple-safer-server"

uv_version_number() {
  uv --version | awk '{print $2}'
}

version_at_least() {
  local actual="$1"
  local minimum="$2"
  local actual_major=0
  local actual_minor=0
  local actual_patch=0
  local minimum_major=0
  local minimum_minor=0
  local minimum_patch=0

  IFS=. read -r actual_major actual_minor actual_patch <<EOF
$actual
EOF
  IFS=. read -r minimum_major minimum_minor minimum_patch <<EOF
$minimum
EOF

  actual_major=${actual_major:-0}
  actual_minor=${actual_minor:-0}
  actual_patch=${actual_patch:-0}
  minimum_major=${minimum_major:-0}
  minimum_minor=${minimum_minor:-0}
  minimum_patch=${minimum_patch:-0}

  if [ "$actual_major" -gt "$minimum_major" ]; then
    return 0
  fi
  if [ "$actual_major" -lt "$minimum_major" ]; then
    return 1
  fi
  if [ "$actual_minor" -gt "$minimum_minor" ]; then
    return 0
  fi
  if [ "$actual_minor" -lt "$minimum_minor" ]; then
    return 1
  fi
  [ "$actual_patch" -ge "$minimum_patch" ]
}

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    current_uv_version=$(uv_version_number)
    if version_at_least "$current_uv_version" "$MIN_UV_VERSION"; then
      echo -e "${GREEN}✔ uv ${current_uv_version} available.${NC}"
      return 0
    fi
    echo -e "${YELLOW}uv ${current_uv_version} found, but SimpleSaferServer needs uv ${MIN_UV_VERSION} or newer for Python 3.14 installs. Installing the latest uv...${NC}"
  else
    echo -e "${YELLOW}uv is not installed. Installing the latest uv...${NC}"
  fi

  TMPFILE=$(mktemp)
  if curl -fLsS "$UV_INSTALL_URL" -o "$TMPFILE"; then
    UV_INSTALL_DIR="$UV_INSTALL_DIR" INSTALLER_NO_MODIFY_PATH=1 sh "$TMPFILE"
    rm -f "$TMPFILE"
  else
    rm -f "$TMPFILE"
    echo -e "${RED}ERROR: Failed to download uv installer.${NC}"
    exit 1
  fi

  # Put the pinned binary first for the rest of this installer even if sudo
  # preserved a user PATH with another uv earlier in the search order.
  export PATH="$UV_INSTALL_DIR:$PATH"
  hash -r

  if ! command -v uv >/dev/null 2>&1; then
    echo -e "${RED}ERROR: uv installation completed but uv is not on PATH.${NC}"
    exit 1
  fi
  installed_uv_version=$(uv_version_number)
  if ! version_at_least "$installed_uv_version" "$MIN_UV_VERSION"; then
    echo -e "${RED}ERROR: expected uv ${MIN_UV_VERSION} or newer, but found uv ${installed_uv_version}.${NC}"
    exit 1
  fi
  echo -e "${GREEN}✔ uv ${installed_uv_version} installed.${NC}"
}

ensure_uv

ensure_service_user() {
  if ! getent group "$APP_GROUP" >/dev/null 2>&1; then
    groupadd --system "$APP_GROUP"
    touch "$SERVICE_GROUP_MARKER"
  fi

  if id "$APP_USER" >/dev/null 2>&1; then
    return 0
  fi

  # The web service should not have a login shell. Root-only work goes through
  # sss-helper instead of giving the web process broad root access.
  useradd \
    --system \
    --gid "$APP_GROUP" \
    --home-dir "$DATA_DIR" \
    --no-create-home \
    --shell /usr/sbin/nologin \
    "$APP_USER"
  touch "$SERVICE_USER_MARKER"
}

install_helper_sudoers() {
  install -d -m 0750 /etc/sudoers.d
  printf '%s ALL=(root) NOPASSWD: %s/sss-helper\n' "$APP_USER" "$BIN_DIR" >"$SUDOERS_FILE"
  chmod 0440 "$SUDOERS_FILE"

  if command -v visudo >/dev/null 2>&1 && ! visudo -cf "$SUDOERS_FILE"; then
    rm -f "$SUDOERS_FILE"
    echo -e "${RED}ERROR:${NC} Refusing to install an invalid sudoers rule for sss-helper."
    exit 1
  fi
}

echo -e "${YELLOW}Preparing service user and app-owned directories...${NC}"
mkdir -p "$DATA_DIR"
ensure_service_user
install -d -o "$APP_USER" -g "$APP_GROUP" -m 0750 "$DATA_DIR"
install -d -o "$APP_USER" -g "$APP_GROUP" -m 0750 "$CONFIG_DIR"
install -d -o "$APP_USER" -g "$APP_GROUP" -m 0750 "$LOG_DIR"
install -d -o "$APP_USER" -g "$APP_GROUP" -m 0750 "$VOLATILE_DIR"
echo -e "${GREEN}✔ Service user and app-owned directories ready.${NC}\n"

# 1. Copy application files. Keep .venv so a clean-layout reinstall can reuse
# the Python environment, but replace every other app file from the selected source tree.
echo -e "${YELLOW}Step 1: Copying application files...${NC}"
mkdir -p "$APP_DIR"
find "$APP_DIR" -mindepth 1 -maxdepth 1 ! -name ".venv" -exec rm -rf -- {} +
tar \
  --exclude="./.git" \
  --exclude="./.venv" \
  --exclude="./scripts" \
  --exclude="./__pycache__" \
  --exclude="*/__pycache__" \
  --exclude="*.pyc" \
  --exclude="*.pyo" \
  --exclude="*.log" \
  -cf - . | (cd "$APP_DIR" && tar -xf -)
echo -e "${GREEN}✔ Application files copied.${NC}\n"

# 2. Create the dedicated uv-managed app environment.
echo -e "${YELLOW}Step 2: Syncing Python runtime and dependencies with uv...${NC}"
(
  cd "$APP_DIR"
  uv python install
  uv sync --frozen --no-dev
)
echo -e "${GREEN}✔ Python environment ready at $VENV_DIR.${NC}\n"

# 3. Install only the public CLI wrappers.
echo -e "${YELLOW}Step 3: Installing CLI wrappers...${NC}"
mkdir -p "$BIN_DIR"
cat >"$BIN_DIR/sss" <<'EOF'
#!/bin/sh
exec /opt/SimpleSaferServer/.venv/bin/python -m simple_safer_server.cli "$@"
EOF
chmod +x "$BIN_DIR/sss"
cat >"$BIN_DIR/sss-helper" <<'EOF'
#!/bin/sh
exec /opt/SimpleSaferServer/.venv/bin/python -m simple_safer_server.privileged_helper "$@"
EOF
chmod +x "$BIN_DIR/sss-helper"
install_helper_sudoers
echo -e "${GREEN}✔ CLI wrappers installed to $BIN_DIR.${NC}\n"

# 4. Install/refresh systemd services for the Web UI and worker.
echo -e "${YELLOW}Step 4: Setting up systemd services...${NC}"
cp simple-safer-server-web.service "$SERVICE_FILE"
cp simple-safer-server-worker.service "$WORKER_SERVICE_FILE"
systemctl daemon-reload
systemctl enable simple-safer-server-web.service
systemctl enable simple-safer-server-worker.service
systemctl restart simple-safer-server-web.service
systemctl restart simple-safer-server-worker.service
echo -e "${GREEN}✔ Systemd services enabled and started.${NC}\n"

# 5. Validate worker task configuration
echo -e "${YELLOW}Step 5: Validating worker task configuration...${NC}"
if sudo -u "$APP_USER" -n "$VENV_DIR/bin/python3" -c "
import sys
sys.path.insert(0, '$APP_DIR')
from simple_safer_server.services.config_manager import ConfigManager
from simple_safer_server.services.runtime import get_runtime
from simple_safer_server.services.system_utils import SystemUtils

rt = get_runtime()
config = ConfigManager(runtime=rt).get_all_config()
# validate_worker_task_config catches exceptions and returns (success, error)
# rather than raising, so we must check the tuple explicitly.
success, error = SystemUtils(runtime=rt).validate_worker_task_config(config)
if not success:
    print(f'Error: {error}', file=sys.stderr)
    sys.exit(1)
"; then
  echo -e "${GREEN}✔ Worker task configuration validated.${NC}\n"
else
  echo -e "${RED}ERROR: Failed to validate worker task configuration.${NC}"
  echo -e "${RED}Scheduled jobs will not run correctly until this is fixed.${NC}"
  echo -e "${YELLOW}Remediation:${NC}"
  echo -e "  1. Check the error message printed above for details."
  echo -e "  2. Review systemd logs with: journalctl -xe"
  echo -e "  3. Fix the reported issue and rerun this installer."
  exit 1
fi

# Print all network interface IPs for user access
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

echo -e "${GREEN}✔ Installation complete!${NC}"
echo -e "${YELLOW}If this is your first install, visit the above address in your browser to complete setup via the web UI.${NC}"
echo -e "${BLUE}===============================================${NC}\n"

# At the end, clean up temporary source files if this was an archive install.
if [ "$CLEANUP_SOURCE" = "1" ]; then
  echo -e "${YELLOW}Cleaning up temporary files...${NC}"
  rm -rf "$TMPDIR"
fi
