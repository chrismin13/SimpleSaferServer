from dataclasses import dataclass
from typing import Any

from simple_safer_server.adapters.command_runner import CommandRunner
from simple_safer_server.services.alerts_service import AlertsService
from simple_safer_server.services.cloud_backup_service import CloudBackupService
from simple_safer_server.services.ddns_service import DdnsService
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
    smb_manager: Any
    user_manager: Any
    task_service: TaskService
    ddns_service: DdnsService
    cloud_backup_service: CloudBackupService
    alerts_service: AlertsService
    storage_service: StorageService
