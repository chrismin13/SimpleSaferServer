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
DATA_DIR="/var/lib/SimpleSaferServer"
OWNERSHIP_MANIFEST="${OWNERSHIP_MANIFEST:-$DATA_DIR/ownership.json}"
VOLATILE_DIR="/run/SimpleSaferServer"
LOG_DIR="/var/log/SimpleSaferServer"
SYSTEMD_DIR="/etc/systemd/system"
APP_USER="sss"
APP_GROUP="sss"
SERVICE_USER_MARKER="$DATA_DIR/.sss-user-created"
SERVICE_GROUP_MARKER="$DATA_DIR/.sss-group-created"
SUDOERS_FILE="/etc/sudoers.d/simple-safer-server"
# Keep Samba-owned paths under one root so tests and recovery runs can redirect
# the whole Samba layout without accidentally reaching the live /etc/samba tree.
SAMBA_DIR="${SAMBA_DIR:-/etc/samba}"
SMB_CONF="${SMB_CONF:-$SAMBA_DIR/smb.conf}"
SSS_SAMBA_GLOBALS_FILE="${SSS_SAMBA_GLOBALS_FILE:-$SAMBA_DIR/simple_safer_server_globals.conf}"
SSS_SAMBA_SHARES_FILE="${SSS_SAMBA_SHARES_FILE:-$SAMBA_DIR/simple_safer_server_shares.conf}"
FSTAB_MARKER="SimpleSaferServer managed backup drive"
SSS_GLOBALS_INCLUDE_BEGIN="# BEGIN SimpleSaferServer global include"
SSS_GLOBALS_INCLUDE_END="# END SimpleSaferServer global include"
SSS_SHARES_INCLUDE_BEGIN="# BEGIN SimpleSaferServer shares include"
SSS_SHARES_INCLUDE_END="# END SimpleSaferServer shares include"
SCRIPT_FILES=(
  sss
  sss-helper
)

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

collect_manifest_resource_identifiers() {
  local module_slug="$1"
  local kind="$2"

  if [ ! -f "$OWNERSHIP_MANIFEST" ]; then
    return 0
  fi

  require_python3 "read $OWNERSHIP_MANIFEST" || return 1

  python3 - "$OWNERSHIP_MANIFEST" "$module_slug" "$kind" <<'PY'
import json
import sys

path, module_slug, kind = sys.argv[1:]

try:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
except Exception:
    raise SystemExit(1)

for item in data.get("resources", []):
    if item.get("module_slug") != module_slug or item.get("kind") != kind:
        continue
    identifier = item.get("identifier")
    if isinstance(identifier, str) and identifier.strip():
        print(identifier.strip())
PY
}

collect_owned_samba_accounts() {
  collect_manifest_resource_identifiers "file-sharing" "samba-account"
}

collect_owned_system_users() {
  collect_manifest_resource_identifiers "file-sharing" "system-user"
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

remove_installer_service_user() {
  local remove_user=0
  local remove_group=0

  if [ -f "$SERVICE_USER_MARKER" ]; then
    remove_user=1
  fi
  if [ -f "$SERVICE_GROUP_MARKER" ]; then
    remove_group=1
  fi

  if [ "$remove_user" -eq 1 ]; then
    userdel "$APP_USER" 2>/dev/null || true
  fi
  if [ "$remove_group" -eq 1 ]; then
    groupdel "$APP_GROUP" 2>/dev/null || true
  fi
}

remove_manifest_owned_accounts() {
  local samba_accounts_output=""
  local system_users_output=""
  local -a SAMBA_ACCOUNTS=()
  local -a SYSTEM_USERS=()

  if ! samba_accounts_output="$(collect_owned_samba_accounts)"; then
    echo "ERROR: Failed to read File Sharing Samba account ownership from $OWNERSHIP_MANIFEST."
    return 1
  fi
  if ! system_users_output="$(collect_owned_system_users)"; then
    echo "ERROR: Failed to read File Sharing system user ownership from $OWNERSHIP_MANIFEST."
    return 1
  fi

  if [ -n "$samba_accounts_output" ]; then
    mapfile -t SAMBA_ACCOUNTS <<<"$samba_accounts_output"
  fi
  if [ -n "$system_users_output" ]; then
    mapfile -t SYSTEM_USERS <<<"$system_users_output"
  fi

  if [ "${#SAMBA_ACCOUNTS[@]}" -gt 0 ]; then
    echo "Removing File Sharing-owned Samba accounts..."
    for username in "${SAMBA_ACCOUNTS[@]}"; do
      echo "Removing Samba account: $username"
      smbpasswd -x "$username" 2>/dev/null || true
    done
  else
    echo "No File Sharing-owned Samba accounts found in $OWNERSHIP_MANIFEST."
  fi

  if [ "${#SYSTEM_USERS[@]}" -gt 0 ]; then
    echo "Removing File Sharing-owned Linux users..."
    for username in "${SYSTEM_USERS[@]}"; do
      echo "Removing Linux user: $username"
      userdel "$username" 2>/dev/null || true
    done
  else
    echo "No File Sharing-owned Linux users found in $OWNERSHIP_MANIFEST."
  fi
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

  if ! python3 - "$original" "$updated" "$FSTAB_MARKER" <<'PY'; then
import sys

original, updated, marker = sys.argv[1:]
with open(original, "r", encoding="utf-8") as handle:
    lines = handle.readlines()

with open(updated, "w", encoding="utf-8") as handle:
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#") or "#" not in line:
            handle.write(line)
            continue

        comment = line.split("#", 1)[1].strip()
        if comment == marker:
            continue
        handle.write(line)
PY
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

remove_owned_samba_include_files() {
  remove_manifest_owned_file "$SSS_SAMBA_GLOBALS_FILE"
  remove_manifest_owned_file "$SSS_SAMBA_SHARES_FILE"
}

ownership_manifest_has_resource() {
  local module_slug="$1"
  local kind="$2"
  local identifier="$3"

  if [ ! -f "$OWNERSHIP_MANIFEST" ]; then
    return 1
  fi

  require_python3 "read $OWNERSHIP_MANIFEST" || return 1

  python3 - "$OWNERSHIP_MANIFEST" "$module_slug" "$kind" "$identifier" <<'PY'
import json
import sys

path, module_slug, kind, identifier = sys.argv[1:]
try:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
except Exception:
    raise SystemExit(1)

for item in payload.get("resources", []):
    if (
        item.get("module_slug") == module_slug
        and item.get("kind") == kind
        and item.get("identifier") == identifier
    ):
        raise SystemExit(0)
raise SystemExit(1)
PY
}

remove_manifest_owned_file() {
  local path="$1"

  if ownership_manifest_has_resource "file-sharing" "config-file" "$path"; then
    rm -f "$path"
  elif [ -e "$path" ]; then
    echo "WARNING: Leaving $path because it is not recorded as owned by File Sharing in $OWNERSHIP_MANIFEST."
  fi
}

samba_include_cleanup_allowed() {
  ownership_manifest_has_resource "file-sharing" "config-file" "$SSS_SAMBA_GLOBALS_FILE" \
    || ownership_manifest_has_resource "file-sharing" "config-file" "$SSS_SAMBA_SHARES_FILE"
}

cleanup_managed_smb_shares() {
  local cleaned=""

  echo "Removing SimpleSaferServer-owned Samba include files..."

  if ! samba_include_cleanup_allowed; then
    echo "No File Sharing ownership records found in $OWNERSHIP_MANIFEST. Leaving Samba config untouched."
    return 0
  fi

  if [ ! -f "$SMB_CONF" ]; then
    remove_owned_samba_include_files
    return 0
  fi

  cleaned="$(make_atomic_temp_file "$SMB_CONF")"

  backup_file_if_present "$SMB_CONF" "uninstall_backup"
  require_python3 "remove SimpleSaferServer Samba include blocks" || return 1

  if ! python3 - "$SMB_CONF" "$cleaned" "$SSS_GLOBALS_INCLUDE_BEGIN" "$SSS_GLOBALS_INCLUDE_END" "$SSS_SHARES_INCLUDE_BEGIN" "$SSS_SHARES_INCLUDE_END" <<'PY'; then
import sys

(
    source,
    cleaned,
    globals_begin,
    globals_end,
    shares_begin,
    shares_end,
) = sys.argv[1:]
with open(source, "r", encoding="utf-8") as handle:
    lines = handle.readlines()

plain_blocks = {
    globals_begin: globals_end,
    shares_begin: shares_end,
}

output = []
index = 0

while index < len(lines):
    stripped = lines[index].strip()

    if stripped in plain_blocks.values():
        raise SystemExit(1)

    if stripped in plain_blocks:
        end_marker = plain_blocks[stripped]
        index += 1
        while index < len(lines):
            inner_stripped = lines[index].strip()
            if inner_stripped == stripped:
                raise SystemExit(1)
            if inner_stripped == end_marker:
                index += 1
                break
            index += 1
        else:
            raise SystemExit(1)
        continue

    output.append(lines[index])
    index += 1

with open(cleaned, "w", encoding="utf-8") as handle:
    handle.writelines(output)
PY
    rm -f "$cleaned"
    remove_owned_samba_include_files
    echo "ERROR: Refusing to rewrite $SMB_CONF because the SimpleSaferServer include markers are malformed."
    echo "WARNING: The owned include files were deleted, but $SMB_CONF may still contain include lines referencing them."
    echo "To fix Samba manually, remove lines referencing simple_safer_server_globals.conf and simple_safer_server_shares.conf from $SMB_CONF, then run: systemctl restart smbd"
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

  remove_owned_samba_include_files

  # Restart smbd so the running service matches the rewritten smb.conf.
  # Best-effort: warn and continue if it fails.
  if ! systemctl restart smbd 2>/dev/null; then
    echo "WARNING: Could not restart smbd. The running Samba service may still reference removed configuration until the next reboot or manual restart."
  fi
}

main() {
  echo -e "${BLUE}===============================================${NC}"
  echo -e "${BLUE}   SimpleSaferServer Uninstaller${NC}"
  echo -e "${BLUE}===============================================${NC}\n"

  if [ "${SSS_FORCE_NON_ROOT_CHECK:-}" = "true" ] || [ "$EUID" -ne 0 ]; then
    echo -e "${RED}ERROR:${NC} Please run as root (sudo)"
    exit 1
  fi

  echo "Starting SimpleSaferServer uninstallation..."
  echo -e "${YELLOW}Active Samba file transfers will be interrupted.${NC}"

  echo "Stopping and disabling systemd units..."
  remove_systemd_unit "simple-safer-server-worker.service"
  remove_systemd_unit "simple-safer-server-web.service"
  rm -f "$SUDOERS_FILE"

  remove_managed_fstab_entries
  cleanup_managed_smb_shares || exit 1

  echo "Removing installed CLI wrappers..."
  for script in "${SCRIPT_FILES[@]}"; do
    rm -f "/usr/local/bin/$script"
    echo "Removed CLI wrapper if present: $script"
  done

  remove_manifest_owned_accounts || exit 1

  remove_installer_service_user

  echo "Removing application files and data..."
  rm -rf "$APP_DIR"
  rm -rf "$CONFIG_DIR"
  rm -rf "$DATA_DIR"
  rm -rf "$VOLATILE_DIR"
  rm -rf "$LOG_DIR"

  echo "Reloading systemd..."
  systemctl daemon-reload 2>/dev/null || true

  echo -e "${GREEN}Uninstallation complete!${NC}"
  echo "SimpleSaferServer application files, services, data, and managed mount entries have been removed."
  echo "Shared system packages and services such as Samba, wsdd2, Python, and rclone were left installed."
  echo "Manifest-owned File Sharing Samba and Linux users were removed."
  echo "SimpleSaferServer-owned Samba include files and include blocks were removed."
  echo "Unmanaged Samba share blocks in $SMB_CONF were left untouched."
}

# Execute main if the script is run directly or piped into bash (e.g. via curl).
# We use "${BASH_SOURCE[0]:-}" to avoid "unbound variable" errors under "set -u"
# when BASH_SOURCE is empty (which happens when reading from standard input).
if [ -z "${BASH_SOURCE[0]:-}" ] || [ "${BASH_SOURCE[0]:-}" = "$0" ]; then
  main "$@"
fi
