from dataclasses import dataclass
from typing import Any

from simple_safer_server.adapters.command_runner import CommandRunner
from simple_safer_server.core.privileged_client import PrivilegedActionClient
from simple_safer_server.modules.alerts.service import AlertsService
from simple_safer_server.modules.cloud_backup.service import CloudBackupService
from simple_safer_server.modules.ddns.service import DdnsService
from simple_safer_server.modules.drive_health.service import DriveHealthSummaryService
from simple_safer_server.modules.storage.service import StorageService
from simple_safer_server.services.server_identity import ServerIdentityService
from simple_safer_server.services.task_service import TaskService


@dataclass(frozen=True)
class AppServices:
    """Application services shared with blueprints through Flask app extensions."""

    runtime: Any
    fake_state: Any
    command_runner: CommandRunner
    privileged_actions: PrivilegedActionClient
    config_manager: Any
    system_utils: Any
    system_updates_manager: Any
    smb_manager: Any
    user_manager: Any
    task_service: TaskService
    ddns_service: DdnsService
    cloud_backup_service: CloudBackupService
    alerts_service: AlertsService
    server_identity_service: ServerIdentityService
    storage_service: StorageService
    drive_health_summary_service: DriveHealthSummaryService
