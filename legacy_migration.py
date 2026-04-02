import configparser
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Union

from werkzeug.security import generate_password_hash

from config_manager import ConfigManager
from runtime import get_runtime
from smb_manager import SMBManager
from system_utils import SystemUtils
from user_manager import PasswordPolicy, UserManager


LOGGER = logging.getLogger(__name__)
LEGACY_BUNDLE_FORMAT = 1
WEB_SERVICE_NAME = "simple_safer_server_web.service"


class MigrationError(Exception):
    pass


@dataclass(frozen=True)
class LegacyBundle:
    bundle_dir: Path
    manifest: dict
    config: Dict[str, str]
    config_path: Path
    msmtp_path: Path
    rclone_path: Path


def _parse_legacy_config(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def _parse_msmtp_config(path: Path) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("host "):
            parsed["smtp_server"] = line.split(" ", 1)[1].strip()
        elif line.startswith("port "):
            parsed["smtp_port"] = line.split(" ", 1)[1].strip()
        elif line.startswith("from "):
            parsed["from_address"] = line.split(" ", 1)[1].strip()
        elif line.startswith("user "):
            parsed["smtp_username"] = line.split(" ", 1)[1].strip()
        elif line.startswith("password "):
            parsed["smtp_password"] = line.split(" ", 1)[1].strip()
    return parsed


def normalize_legacy_backup_time(value: str) -> str:
    parts = value.strip().split(":")
    if len(parts) not in {2, 3}:
        raise MigrationError(
            f"Legacy backup time '{value}' is invalid. Expected HH:MM or HH:MM:SS."
        )

    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise MigrationError(f"Legacy backup time '{value}' is invalid.") from exc

    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise MigrationError(
            f"Legacy backup time '{value}' is out of range. Expected 00:00 to 23:59."
        )

    return f"{hour:02d}:{minute:02d}"


def load_legacy_bundle(bundle_dir: Union[str, Path]) -> LegacyBundle:
    bundle_path = Path(bundle_dir).resolve()
    if not bundle_path.is_dir():
        raise MigrationError(f"Legacy bundle directory not found: {bundle_path}")

    manifest_path = bundle_path / "manifest.json"
    config_path = bundle_path / "config.conf"
    msmtp_path = bundle_path / "msmtprc"
    rclone_path = bundle_path / "rclone.conf"

    if not config_path.exists():
        raise MigrationError(f"Missing legacy config bundle file: {config_path}")
    if not msmtp_path.exists():
        raise MigrationError(f"Missing legacy SMTP bundle file: {msmtp_path}")
    if not rclone_path.exists():
        raise MigrationError(f"Missing legacy rclone bundle file: {rclone_path}")

    manifest: dict = {}
    if manifest_path.exists():
        import json

        manifest = json.loads(manifest_path.read_text())
        version = manifest.get("format_version")
        if version != LEGACY_BUNDLE_FORMAT:
            raise MigrationError(
                f"Unsupported legacy bundle format '{version}'. Expected {LEGACY_BUNDLE_FORMAT}."
            )

    config = _parse_legacy_config(config_path)
    required_keys = [
        "EMAIL_ADDRESS",
        "SERVER_NAME",
        "UUID",
        "MOUNT_POINT",
        "RCLONE_DIR",
        "BACKUP_CLOUD_TIME",
    ]
    missing = [key for key in required_keys if not config.get(key)]
    if missing:
        raise MigrationError(
            "Legacy config is missing required values: " + ", ".join(sorted(missing))
        )

    return LegacyBundle(
        bundle_dir=bundle_path,
        manifest=manifest,
        config=config,
        config_path=config_path,
        msmtp_path=msmtp_path,
        rclone_path=rclone_path,
    )


def _backup_existing_file(source: Path, backup_dir: Path, backup_name: str) -> None:
    if not source.exists():
        return
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, backup_dir / backup_name)


def _write_preserved_file(source: Path, target: Path, *, mode: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    target.chmod(mode)


def _ensure_admin_user(user_manager: UserManager, username: str, password: str) -> str:
    user_manager.users = user_manager._load_users()

    if not re.match(r"^[a-zA-Z0-9_-]{3,32}$", username):
        raise MigrationError(
            "Username must be 3-32 characters and contain only letters, numbers, underscores, and hyphens."
        )

    policy = PasswordPolicy()
    valid, message = policy.validate(password)
    if not valid:
        raise MigrationError(message)

    if username in user_manager.users:
        other_users = [name for name in user_manager.users if name != username]
        if other_users:
            raise MigrationError(
                "Cannot reuse existing admin user because other SimpleSaferServer users already exist."
            )

        user = user_manager.users[username]
        user["password_hash"] = generate_password_hash(password)
        user["is_admin"] = True
        user["failed_attempts"] = 0
        user["locked_until"] = None
        user.setdefault("created_at", str(datetime.utcnow()))
        user.setdefault("last_login", None)
        user_manager._save_users()

        if not user_manager._sync_user_to_samba(username, password):
            raise MigrationError(
                f"Failed to sync the existing admin user '{username}' into Samba."
            )
        return "updated"

    if user_manager.users:
        raise MigrationError(
            "SimpleSaferServer users already exist on this system. Refusing to overwrite them during legacy migration."
        )

    success, message = user_manager.create_user(username, password)
    if not success:
        raise MigrationError(message)
    return "created"


def _install_system_tasks(system_utils: SystemUtils, config: dict) -> None:
    ok, error = system_utils.create_systemd_config_file(config)
    if not ok:
        raise MigrationError(f"Failed to create systemd config: {error}")

    ok, error = system_utils.install_systemd_scripts(config)
    if not ok:
        raise MigrationError(f"Failed to install task scripts: {error}")

    ok, error = system_utils.install_systemd_services_and_timers(config)
    if not ok:
        raise MigrationError(f"Failed to install systemd services and timers: {error}")


def _configure_backup_share(
    smb_manager: SMBManager,
    user_manager: UserManager,
    *,
    mount_point: str,
    admin_username: str,
) -> None:
    runtime = smb_manager.runtime

    if runtime.is_fake:
        existing_shares = smb_manager.get_shares()
        if any(share["name"] == "backup" for share in existing_shares):
            smb_manager.update_share(
                old_name="backup",
                new_name="backup",
                path=mount_point,
                writable=True,
                comment="Fake-mode backup share",
                valid_users=[admin_username],
            )
        else:
            smb_manager.add_share(
                name="backup",
                path=mount_point,
                writable=True,
                comment="Fake-mode backup share",
                valid_users=[admin_username],
            )
        return

    user_manager.users = user_manager._load_users()
    if admin_username not in user_manager.users:
        raise MigrationError(f"Admin user '{admin_username}' was not found in the user database.")

    if not user_manager.user_exists_in_samba(admin_username):
        raise MigrationError(
            f"Admin user '{admin_username}' is missing from Samba after migration."
        )

    existing_shares = smb_manager.get_shares()
    if any(share["name"] == "backup" for share in existing_shares):
        smb_manager.update_share(
            old_name="backup",
            new_name="backup",
            path=mount_point,
            writable=True,
            comment="Default backup share created by SimpleSaferServer migration",
            valid_users=[admin_username],
        )
    else:
        smb_manager.add_share(
            name="backup",
            path=mount_point,
            writable=True,
            comment="Default backup share created by SimpleSaferServer migration",
            valid_users=[admin_username],
        )

    try:
        subprocess.run(["systemctl", "enable", "smbd"], check=True)
        subprocess.run(["systemctl", "enable", "nmbd"], check=True)
    except subprocess.CalledProcessError as exc:
        LOGGER.warning("Failed to enable SMB services for boot: %s", exc)


def _restart_web_service(runtime) -> None:
    if runtime.is_fake:
        return
    subprocess.run(["systemctl", "restart", WEB_SERVICE_NAME], check=True)


def import_legacy_bundle(bundle_dir: Union[str, Path], *, admin_username: str, admin_password: str) -> dict:
    runtime = get_runtime()
    if not runtime.is_fake and os.geteuid() != 0:
        raise MigrationError("Legacy import must be run as root.")

    bundle = load_legacy_bundle(bundle_dir)
    config_manager = ConfigManager(runtime=runtime)
    system_utils = SystemUtils(runtime=runtime)
    user_manager = UserManager(runtime=runtime)
    smb_manager = SMBManager(runtime=runtime)

    backup_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = runtime.config_dir / "migration-backups" / backup_timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    _backup_existing_file(config_manager.config_path, backup_dir, "config.conf")
    _backup_existing_file(user_manager.users_file, backup_dir, "users.json")
    _backup_existing_file(runtime.msmtp_config_path, backup_dir, "msmtprc")
    _backup_existing_file(runtime.rclone_config_dir / "rclone.conf", backup_dir, "rclone.conf")

    legacy_config = bundle.config
    msmtp_config = _parse_msmtp_config(bundle.msmtp_path)
    backup_time = normalize_legacy_backup_time(legacy_config["BACKUP_CLOUD_TIME"])
    from_address = (
        msmtp_config.get("from_address")
        or msmtp_config.get("smtp_username")
        or legacy_config["EMAIL_ADDRESS"]
    )

    config_manager.config = configparser.ConfigParser()
    config_manager.config["system"] = {
        "username": admin_username,
        "server_name": legacy_config["SERVER_NAME"],
        "setup_complete": "false",
    }
    config_manager.config["backup"] = {
        "email_address": legacy_config["EMAIL_ADDRESS"],
        "from_address": from_address,
        "uuid": legacy_config["UUID"],
        "usb_id": legacy_config.get("USB_ID", ""),
        "mount_point": legacy_config["MOUNT_POINT"],
        "rclone_dir": legacy_config["RCLONE_DIR"],
        "bandwidth_limit": legacy_config.get("BANDWIDTH_LIMIT", ""),
        "cloud_mode": "advanced",
        "mega_email": "",
        "mega_pass": "",
        "mega_folder": "",
    }
    config_manager.config["schedule"] = {
        "backup_cloud_time": backup_time,
    }
    config_manager.config["hdsentinel"] = {
        "enabled": "true",
        "health_change_alert": "true",
    }
    config_manager.save_config()

    _write_preserved_file(bundle.msmtp_path, runtime.msmtp_config_path, mode=0o600)
    _write_preserved_file(bundle.rclone_path, runtime.rclone_config_dir / "rclone.conf", mode=0o600)

    admin_action = _ensure_admin_user(user_manager, admin_username, admin_password)
    config = config_manager.get_all_config()
    _install_system_tasks(system_utils, config)
    _configure_backup_share(
        smb_manager,
        user_manager,
        mount_point=config["backup"]["mount_point"],
        admin_username=admin_username,
    )

    config_manager.mark_setup_complete()
    _restart_web_service(runtime)

    return {
        "admin_username": admin_username,
        "admin_action": admin_action,
        "backup_time": backup_time,
        "backup_dir": str(backup_dir),
        "mount_point": config["backup"]["mount_point"],
        "rclone_dir": config["backup"]["rclone_dir"],
    }
