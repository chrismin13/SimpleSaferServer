from __future__ import annotations

import os
from typing import Any

from simple_safer_server.adapters.rclone import RcloneAdapter
from simple_safer_server.core.job_action_client import run_privileged_job_action
from simple_safer_server.modules.alerts.notifications import AlertNotifier
from simple_safer_server.modules.cloud_backup.service import strict_cloud_enabled
from simple_safer_server.modules.storage.location import (
    StorageLocationError,
    validate_storage_ready_for_backup,
)
from simple_safer_server.services.config_manager import ConfigManager
from simple_safer_server.services.runtime import get_runtime
from simple_safer_server.services.system_utils import SystemUtils
from simple_safer_server.web.problems import ValidationProblem


def _send_failure_alert(config_manager: Any, runtime: Any, title: str, message: str) -> None:
    print(f"{title} - {message}")
    AlertNotifier(config_manager, runtime).notify(
        title,
        message,
        alert_type="error",
        source="backup_cloud",
    )


def run_backup_job_direct(
    *,
    runtime: Any | None = None,
    config_manager: Any | None = None,
    system_utils: Any | None = None,
    rclone_adapter: RcloneAdapter | None = None,
) -> int:
    """Run Cloud Backup inside the helper process without a shell wrapper."""
    runtime = runtime or get_runtime()
    config_manager = config_manager or ConfigManager(runtime=runtime)
    system_utils = system_utils or SystemUtils(runtime=runtime)
    rclone_adapter = rclone_adapter or RcloneAdapter()

    print("Starting cloud backup process...")
    try:
        cloud_enabled = strict_cloud_enabled(
            config_manager.get_value("backup", "cloud_enabled", None)
        )
    except ValidationProblem:
        _send_failure_alert(
            config_manager,
            runtime,
            "BACKUP TO CLOUD FAILED - Cloud Backup Setting Invalid",
            "Cloud backup could not start because backup.cloud_enabled is missing or invalid. "
            "Save Cloud Backup settings in the web interface.",
        )
        return 1
    if not cloud_enabled:
        print("Cloud backup is disabled.")
        return 0

    mount_point = config_manager.get_value("backup", "mount_point", runtime.default_mount_point)
    rclone_dir = (config_manager.get_value("backup", "rclone_dir", "") or "").strip()
    bandwidth_limit = (
        config_manager.get_value("backup", "bandwidth_limit", "") or ""
    ).strip()

    try:
        location = validate_storage_ready_for_backup(
            config_manager,
            system_utils,
            runtime=runtime,
        )
    except StorageLocationError:
        _send_failure_alert(
            config_manager,
            runtime,
            "BACKUP TO CLOUD FAILED - Storage Source Check Failed",
            f"SimpleSaferServer could not verify the storage source at {mount_point}. "
            "Cloud backup was stopped so it would not sync the wrong or empty folder.",
        )
        return 1

    if not os.access(location.path, os.R_OK):
        _send_failure_alert(
            config_manager,
            runtime,
            "BACKUP TO CLOUD FAILED - Drive has IO Errors",
            f"Check the connection to the Hard Drive at {location.path}!",
        )
        return 1

    if not rclone_dir:
        _send_failure_alert(
            config_manager,
            runtime,
            "BACKUP TO CLOUD FAILED - No Rclone Directory Configured",
            "Please configure the cloud backup destination in the web interface.",
        )
        return 1

    rclone_config = runtime.rclone_config_dir / "rclone.conf"
    print(f"Starting cloud backup to {rclone_dir}...")
    print(f"Source: {location.path}")
    print(f"Destination: {rclone_dir}")
    proc = rclone_adapter.sync(
        str(location.path),
        rclone_dir,
        config_path=str(rclone_config),
        bandwidth_limit=bandwidth_limit,
    )
    stdout, stderr = proc.communicate()
    output = "\n".join(part.strip() for part in (stdout, stderr) if part and part.strip())
    if proc.returncode != 0:
        _send_failure_alert(
            config_manager,
            runtime,
            "BACKUP TO CLOUD FAILED - Unknown Error",
            f"Backup failed.\n\n{output}" if output else "Backup failed.",
        )
        return 1

    if output:
        print(output)
    print("Cloud backup completed successfully")
    return 0


def run_backup_job() -> int:
    """Request Cloud Backup through the allowlisted privileged helper."""
    return run_privileged_job_action("cloud-backup.sync")
