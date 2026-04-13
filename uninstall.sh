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
USERS_FILE="$CONFIG_DIR/users.json"
DATA_DIR="/var/lib/SimpleSaferServer"
LOG_DIR="/var/log/SimpleSaferServer"
SYSTEMD_DIR="/etc/systemd/system"
SMB_CONF="/etc/samba/smb.conf"
TMP_DIR=""
FSTAB_MARKER="SimpleSaferServer managed backup drive"
LEGACY_FSTAB_MARKER="SimpleSaferServer"
MANAGED_SHARE_BEGIN_PREFIX="# BEGIN SimpleSaferServer share: "
MANAGED_SHARE_END_PREFIX="# END SimpleSaferServer share: "
SCRIPT_FILES=(
  check_mount.sh
  check_health.sh
  check_health.py
  backup_cloud.sh
  predict_health.py
  log_alert.py
  import_legacy.py
)

# The installer writes rclone config where the root-owned scheduled tasks can
# read it later, so the uninstaller needs to look there instead of under /etc.
ROOT_HOME="$(getent passwd root 2>/dev/null | cut -d: -f6)"
if [ -z "$ROOT_HOME" ]; then
    ROOT_HOME="/root"
fi
RCLONE_CONFIG_DIR="$ROOT_HOME/.config/rclone"
RCLONE_CONFIG_PATH="$RCLONE_CONFIG_DIR/rclone.conf"

setup_temp_dir() {
    if [ -z "$TMP_DIR" ]; then
        TMP_DIR="$(mktemp -d)"
    fi
}

cleanup() {
    if [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ]; then
        rm -rf "$TMP_DIR"
    fi
    TMP_DIR=""
}

collect_samba_users() {
    if [ ! -f "$USERS_FILE" ]; then
        return 0
    fi

    python3 - "$USERS_FILE" <<'PY'
import json
import sys

path = sys.argv[1]

try:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
except Exception:
    raise SystemExit(0)

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

    setup_temp_dir
    updated="$TMP_DIR/fstab.updated"

    if [ ! -f "$original" ]; then
        return 0
    fi

    echo "Removing SimpleSaferServer-managed /etc/fstab entries..."
    backup_file_if_present "$original" "uninstall_backup"

    if ! awk -v marker="$FSTAB_MARKER" -v legacy="$LEGACY_FSTAB_MARKER" '
    function trim(value) {
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
        return value
    }

    {
        if ($0 ~ /^[[:space:]]*#/ || index($0, "#") == 0) {
            print
            next
        }

        comment = trim(substr($0, index($0, "#") + 1))
        if (comment == marker || comment == legacy) {
            next
        }

        print
    }
    ' "$original" > "$updated"; then
        rm -f "$updated"
        echo "ERROR: Failed to rebuild $original while removing SimpleSaferServer-managed entries."
        return 1
    fi

    # Refuse to replace core system files only if the filtering step failed to
    # produce the temporary output file at all. An empty file is valid when all
    # entries were SimpleSaferServer-managed and have been removed.
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

    setup_temp_dir
    cleaned="$TMP_DIR/smb.conf.cleaned"

    echo "Removing SimpleSaferServer-managed Samba shares..."
    backup_file_if_present "$SMB_CONF" "uninstall_backup"

    if ! awk -v begin_prefix="$MANAGED_SHARE_BEGIN_PREFIX" -v end_prefix="$MANAGED_SHARE_END_PREFIX" '
    BEGIN {
        in_managed_share = 0
        current_share_name = ""
        bad = 0
    }

    {
        line = $0
        sub(/^[[:space:]]+/, "", line)

        if (index(line, begin_prefix) == 1) {
            share_name = substr(line, length(begin_prefix) + 1)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", share_name)

            if (in_managed_share || share_name == "") {
                bad = 1
                exit 1
            }

            in_managed_share = 1
            current_share_name = share_name
            next
        }

        if (index(line, end_prefix) == 1) {
            share_name = substr(line, length(end_prefix) + 1)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", share_name)

            if (!in_managed_share || share_name == "" || share_name != current_share_name) {
                bad = 1
                exit 1
            }

            in_managed_share = 0
            current_share_name = ""
            next
        }

        if (!in_managed_share) {
            print
        }
    }

    END {
        if (in_managed_share) {
            bad = 1
        }

        if (bad) {
            exit 1
        }
    }
    ' "$SMB_CONF" > "$cleaned"
    then
        rm -f "$cleaned"
        echo "ERROR: Refusing to rewrite $SMB_CONF because the SimpleSaferServer share markers are malformed."
        return 1
    fi

    # Keep the live Samba config untouched if the cleaned candidate was not
    # produced as expected.
    if [ ! -s "$cleaned" ]; then
        rm -f "$cleaned"
        echo "ERROR: Refusing to replace $SMB_CONF because the generated file is missing or empty."
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

main() {
    trap cleanup EXIT
    setup_temp_dir

    echo -e "${BLUE}==============================================="
    echo -e "   SimpleSaferServer Uninstaller"
    echo -e "===============================================${NC}\n"

    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}ERROR:${NC} Please run as root (sudo)"
        exit 1
    fi

    echo "Starting SimpleSaferServer uninstallation..."

    echo "Stopping and disabling systemd units..."
    for svc in check_mount check_health backup_cloud; do
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
    mapfile -t SAMBA_USERS < <(collect_samba_users)
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
    rm -rf "$LOG_DIR"

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
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
