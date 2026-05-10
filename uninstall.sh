#!/bin/bash

set -euo pipefail

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
NC='\033[0m' # No Color

APP_DIR="/opt/SimpleSaferServer"
CONFIG_DIR="/etc/SimpleSaferServer"
CONFIG_FILE="$CONFIG_DIR/config.conf"
USERS_FILE="$CONFIG_DIR/users.json"
DATA_DIR="/var/lib/SimpleSaferServer"
VOLATILE_DIR="/run/SimpleSaferServer"
LOG_DIR="/var/log/SimpleSaferServer"
SYSTEMD_DIR="/etc/systemd/system"
SMB_CONF="/etc/samba/smb.conf"
APT_AUTO_UPGRADES_CONF="/etc/apt/apt.conf.d/20auto-upgrades"
FSTAB_MARKER="SimpleSaferServer managed backup drive"
LEGACY_FSTAB_MARKER="SimpleSaferServer"
MANAGED_SHARE_BEGIN_PREFIX="# BEGIN SimpleSaferServer share: "
MANAGED_SHARE_END_PREFIX="# END SimpleSaferServer share: "
SCRIPT_FILES=(
  check_mount.sh
  check_health.sh
  check_health.py
  backup_cloud.sh
  log_alert.py
  import_legacy.py
  ddns_update.sh
  ddns_update.py
  app_update.sh
  app_update.py
)

# The installer writes rclone config where the root-owned scheduled tasks can
# read it later, so the uninstaller needs to look there instead of under /etc.
ROOT_HOME=""
if command -v getent >/dev/null 2>&1; then
    ROOT_HOME="$(getent passwd root 2>/dev/null | cut -d: -f6 || true)"
fi
if [ -z "$ROOT_HOME" ]; then
    ROOT_HOME="/root"
fi
RCLONE_CONFIG_DIR="$ROOT_HOME/.config/rclone"
RCLONE_CONFIG_PATH="$RCLONE_CONFIG_DIR/rclone.conf"

make_atomic_temp_file() {
    local target_path="$1"
    local target_dir=""
    local target_name=""

    target_dir="$(dirname -- "$target_path")"
    target_name="$(basename -- "$target_path")"
    mktemp "${target_dir}/.${target_name}.XXXXXX"
}

require_python3() {
    local reason="$1"
    if ! command -v python3 >/dev/null 2>&1; then
        echo "ERROR: python3 is required to $reason during uninstall." >&2
        return 1
    fi
}

collect_samba_users() {
    if [ ! -f "$USERS_FILE" ]; then
        return 0
    fi

    require_python3 "read $USERS_FILE" || return 1

    python3 - "$USERS_FILE" <<'PY'
import json
import sys

path = sys.argv[1]

try:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
except Exception:
    raise SystemExit(1)

if isinstance(data, dict):
    for username in data.keys():
        if isinstance(username, str) and username.strip():
            print(username)
elif isinstance(data, list):
    for item in data:
        if isinstance(item, dict):
            username = item.get("username")
            if isinstance(username, str) and username.strip():
                print(username)
PY
}

apt_updates_were_managed() {
    if [ ! -f "$CONFIG_FILE" ]; then
        return 1
    fi

    require_python3 "read $CONFIG_FILE" || return 1

    python3 - "$CONFIG_FILE" <<'PY'
import configparser
import sys

config = configparser.ConfigParser()
config.read(sys.argv[1])
if config.getboolean("apt_updates", "managed", fallback=False):
    raise SystemExit(0)
raise SystemExit(1)
PY
}

livepatch_was_managed() {
    if [ ! -f "$CONFIG_FILE" ]; then
        return 1
    fi

    require_python3 "read $CONFIG_FILE" || return 1

    python3 - "$CONFIG_FILE" <<'PY'
import configparser
import sys

config = configparser.ConfigParser()
config.read(sys.argv[1])
if config.getboolean("system_updates", "livepatch_managed", fallback=False):
    raise SystemExit(0)
raise SystemExit(1)
PY
}

managed_hostname_summary() {
    if [ ! -f "$CONFIG_FILE" ]; then
        return 0
    fi

    require_python3 "read hostname metadata from $CONFIG_FILE" || return 1

    python3 - "$CONFIG_FILE" <<'PY'
import configparser
import socket
import sys

config = configparser.ConfigParser()
config.read(sys.argv[1])
if not config.getboolean("system", "hostname_managed", fallback=False):
    raise SystemExit(0)

original = config.get("system", "original_hostname", fallback="").strip()
applied = config.get("system", "applied_hostname", fallback="").strip()
current = socket.gethostname().strip()
print("original={}".format(original))
print("applied={}".format(applied))
print("current={}".format(current))
PY
}

backup_file_if_present() {
    local path="$1"
    local label="$2"
    local timestamp=""
    local backup_path=""

    if [ ! -f "$path" ]; then
        return 0
    fi

    timestamp=$(date +"%Y%m%d_%H%M%S")
    backup_path="${path}.${label}.${timestamp}"
    cp "$path" "$backup_path"
    echo "Created backup: $backup_path"
}

remove_systemd_unit() {
    local unit="$1"

    systemctl stop "$unit" 2>/dev/null || true
    systemctl disable "$unit" 2>/dev/null || true
    rm -f "$SYSTEMD_DIR/$unit"
}

remove_managed_fstab_entries() {
    local original="${1:-/etc/fstab}"
    local updated=""

    if [ ! -f "$original" ]; then
        return 0
    fi

    updated="$(make_atomic_temp_file "$original")"

    echo "Removing SimpleSaferServer-managed /etc/fstab entries..."
    backup_file_if_present "$original" "uninstall_backup"
    require_python3 "remove managed fstab entries" || return 1

    if ! python3 - "$original" "$updated" "$FSTAB_MARKER" "$LEGACY_FSTAB_MARKER" <<'PY'
import sys

original, updated, marker, legacy = sys.argv[1:]
with open(original, "r", encoding="utf-8") as handle:
    lines = handle.readlines()

with open(updated, "w", encoding="utf-8") as handle:
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#") or "#" not in line:
            handle.write(line)
            continue

        comment = line.split("#", 1)[1].strip()
        if comment in {marker, legacy}:
            continue
        handle.write(line)
PY
    then
        rm -f "$updated"
        echo "ERROR: Failed to rebuild $original while removing SimpleSaferServer-managed entries."
        return 1
    fi

    # Allow intentionally empty results, but never replace a core config with a
    # missing temp file if the rewrite step failed before producing output.
    if [ ! -f "$updated" ]; then
        rm -f "$updated"
        echo "ERROR: Refusing to replace $original because the generated file is missing."
        return 1
    fi

    if ! mv "$updated" "$original"; then
        rm -f "$updated"
        echo "ERROR: Failed to replace $original."
        return 1
    fi

    if ! chmod 644 "$original"; then
        echo "ERROR: Failed to set permissions on $original."
        return 1
    fi
}

cleanup_managed_smb_shares() {
    local cleaned=""

    if [ ! -f "$SMB_CONF" ]; then
        return 0
    fi

    cleaned="$(make_atomic_temp_file "$SMB_CONF")"

    echo "Removing SimpleSaferServer-managed Samba shares..."
    backup_file_if_present "$SMB_CONF" "uninstall_backup"
    require_python3 "remove managed Samba shares" || return 1

    if ! python3 - "$SMB_CONF" "$cleaned" "$MANAGED_SHARE_BEGIN_PREFIX" "$MANAGED_SHARE_END_PREFIX" <<'PY'
import sys

source, cleaned, begin_prefix, end_prefix = sys.argv[1:]
with open(source, "r", encoding="utf-8") as handle:
    lines = handle.readlines()

output = []
in_managed_share = False
current_share_name = ""

for line in lines:
    stripped = line.lstrip()
    if stripped.startswith(begin_prefix):
        share_name = stripped[len(begin_prefix):].strip()
        if in_managed_share or not share_name:
            raise SystemExit(1)
        in_managed_share = True
        current_share_name = share_name
        continue

    if stripped.startswith(end_prefix):
        share_name = stripped[len(end_prefix):].strip()
        if not in_managed_share or not share_name or share_name != current_share_name:
            raise SystemExit(1)
        in_managed_share = False
        current_share_name = ""
        continue

    if not in_managed_share:
        output.append(line)

if in_managed_share:
    raise SystemExit(1)

with open(cleaned, "w", encoding="utf-8") as handle:
    handle.writelines(output)
PY
    then
        rm -f "$cleaned"
        echo "ERROR: Refusing to rewrite $SMB_CONF because the SimpleSaferServer share markers are malformed."
        return 1
    fi

    # Allow smb.conf to become empty if every block was owned by
    # SimpleSaferServer, but never replace it with a missing temp file.
    if [ ! -f "$cleaned" ]; then
        rm -f "$cleaned"
        echo "ERROR: Refusing to replace $SMB_CONF because the generated file is missing."
        return 1
    fi

    if ! mv "$cleaned" "$SMB_CONF"; then
        rm -f "$cleaned"
        echo "ERROR: Failed to replace $SMB_CONF."
        return 1
    fi

    if ! chmod 644 "$SMB_CONF"; then
        echo "ERROR: Failed to set permissions on $SMB_CONF."
        return 1
    fi

    systemctl restart smbd 2>/dev/null || true
    systemctl restart nmbd 2>/dev/null || true
}

remove_git_safe_directory() {
    local repo_path="${1:-$APP_DIR}"

    if ! command -v git >/dev/null 2>&1; then
        return 0
    fi

    # The installer adds this so root-run systemd services can inspect the
    # admin-owned app checkout. Remove every matching value because repeated
    # reinstalls before this cleanup may have written duplicates.
    git config --system --unset-all safe.directory "$repo_path" 2>/dev/null || true
}

main() {
    echo -e "${BLUE}===============================================${NC}"
    echo -e "${BLUE}   SimpleSaferServer Uninstaller${NC}"
    echo -e "${BLUE}===============================================${NC}\n"

    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}ERROR:${NC} Please run as root (sudo)"
        exit 1
    fi

    echo "Starting SimpleSaferServer uninstallation..."

    # Read this before CONFIG_DIR is removed so the final report can tell the
    # admin about OS-level apt settings that intentionally survive uninstall.
    local apt_updates_managed="false"
    if apt_updates_were_managed; then
        apt_updates_managed="true"
    fi
    local livepatch_managed="false"
    if livepatch_was_managed; then
        livepatch_managed="true"
    fi
    local hostname_summary=""
    if ! hostname_summary="$(managed_hostname_summary)"; then
        echo "ERROR: Failed to read SimpleSaferServer hostname metadata from $CONFIG_FILE."
        exit 1
    fi

    echo "Stopping and disabling systemd units..."
    for svc in check_mount check_health backup_cloud ddns_update app_update; do
        remove_systemd_unit "${svc}.timer"
        remove_systemd_unit "${svc}.service"
    done
    remove_systemd_unit "simple_safer_server_web.service"

    remove_managed_fstab_entries
    cleanup_managed_smb_shares || exit 1

    echo "Removing installed helper scripts..."
    for script in "${SCRIPT_FILES[@]}"; do
        rm -f "$APP_DIR/scripts/$script"
        rm -f "/usr/local/bin/$script"
        echo "Removed helper script if present: $script"
    done

    echo "Removing installed binary and legacy model artifacts..."
    rm -f /usr/local/bin/hdsentinel
    rm -f /usr/local/bin/xgb_model.json
    rm -f /usr/local/bin/optimal_threshold_xgb.pkl
    rm -rf "$APP_DIR/harddrive_model"

    # Gather Samba usernames before deleting the config directory because the
    # app stores the source of truth in users.json rather than in a manifest.
    local samba_users_output=""
    local -a SAMBA_USERS=()
    if ! samba_users_output="$(collect_samba_users)"; then
        echo "ERROR: Failed to read SimpleSaferServer users from $USERS_FILE."
        exit 1
    fi
    if [ -n "$samba_users_output" ]; then
        mapfile -t SAMBA_USERS <<< "$samba_users_output"
    fi

    if [ "${#SAMBA_USERS[@]}" -gt 0 ]; then
        echo "Removing SimpleSaferServer users from Samba..."
        for username in "${SAMBA_USERS[@]}"; do
            echo "Removing Samba user: $username"
            smbpasswd -x "$username" 2>/dev/null || true
        done
    else
        echo "No SimpleSaferServer Samba users found in $USERS_FILE."
    fi

    echo "Removing application files and data..."
    rm -rf "$APP_DIR"
    rm -rf "$CONFIG_DIR"
    rm -rf "$DATA_DIR"
    rm -rf "$VOLATILE_DIR"
    rm -rf "$LOG_DIR"

    echo "Removing SimpleSaferServer Git trust entry if present..."
    remove_git_safe_directory "$APP_DIR"

    echo "Removing SimpleSaferServer rclone configuration if present..."
    rm -f "$RCLONE_CONFIG_PATH"
    rmdir "$RCLONE_CONFIG_DIR" 2>/dev/null || true

    echo "Removing legacy SimpleSaferServer user and group if present..."
    userdel -r SimpleSaferServer 2>/dev/null || true
    groupdel SimpleSaferServer 2>/dev/null || true

    echo "Reloading systemd..."
    systemctl daemon-reload 2>/dev/null || true

    echo -e "${GREEN}Uninstallation complete!${NC}"
    echo "SimpleSaferServer application files, services, timers, data, and managed mount entries have been removed."
    echo "Shared system packages such as Samba, Python, and rclone were left installed."
    echo "Samba user accounts created from SimpleSaferServer users were removed."
    echo "Marker-wrapped SimpleSaferServer-managed Samba share blocks were removed from $SMB_CONF."
    echo "Unmanaged or legacy untagged Samba share blocks were left untouched."
    if [ "$apt_updates_managed" = "true" ]; then
        echo "SimpleSaferServer had managed apt periodic settings in $APT_AUTO_UPGRADES_CONF."
        echo "That file was left in place. Review it manually if you want to disable automatic apt updates."
    fi
    if [ "$livepatch_managed" = "true" ]; then
        echo "SimpleSaferServer enabled Ubuntu Livepatch through Ubuntu Pro integration."
        echo "Ubuntu Pro and Livepatch state were left in place."
        echo "Review or disable them manually if you do not want them after uninstall."
    fi
    if [ -n "$hostname_summary" ]; then
        local original_hostname=""
        local applied_hostname=""
        local current_hostname=""
        while IFS='=' read -r key value; do
            case "$key" in
                original) original_hostname="$value" ;;
                applied) applied_hostname="$value" ;;
                current) current_hostname="$value" ;;
            esac
        done <<< "$hostname_summary"

        echo "SimpleSaferServer changed this server's hostname during setup or management."
        if [ -n "$original_hostname" ] && [ -n "$applied_hostname" ]; then
            echo "Original hostname: $original_hostname"
            echo "Last SimpleSaferServer-applied hostname: $applied_hostname"
        fi
        if [ -n "$current_hostname" ] && [ "$current_hostname" != "$applied_hostname" ]; then
            echo "Current hostname: $current_hostname"
        fi
        echo "The hostname and /etc/hosts were left in place. Change them manually if you want a different server name after uninstall."
    fi
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
