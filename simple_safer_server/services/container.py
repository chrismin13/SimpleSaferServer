from dataclasses import dataclass
from typing import Any

from simple_safer_server.adapters.command_runner import CommandRunner
from simple_safer_server.services.alerts_service import AlertsService
from simple_safer_server.services.app_updates import AppUpdateManager
from simple_safer_server.services.cloud_backup_service import CloudBackupService
from simple_safer_server.services.ddns_service import DdnsService
from simple_safer_server.services.drive_health import DriveHealthSummaryService
from simple_safer_server.services.server_identity import ServerIdentityService
from simple_safer_server.services.storage_service import StorageService
from simple_safer_server.services.task_service import TaskService


@dataclass(frozen=True)
class AppServices:
    """Application services shared with blueprints through Flask app extensions."""

    runtime: Any
    fake_state: Any
    command_runner: CommandRunner
    config_manager: Any
    system_utils: Any
    system_updates_manager: Any
    app_update_manager: AppUpdateManager
    smb_manager: Any
    user_manager: Any
    task_service: TaskService
    ddns_service: DdnsService
    cloud_backup_service: CloudBackupService
    alerts_service: AlertsService
    server_identity_service: ServerIdentityService
    storage_service: StorageService
    drive_health_summary_service: DriveHealthSummaryService
