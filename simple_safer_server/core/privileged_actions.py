from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TextIO

from simple_safer_server.services.runtime import get_runtime

PrivilegedActionHandler = Callable[[dict[str, Any], Any], dict[str, Any]]


class PrivilegedActionError(RuntimeError):
    """Raised when an allowlisted privileged action cannot run safely."""


@dataclass(frozen=True)
class PrivilegedActionResult:
    action: str
    data: dict[str, Any]


class PrivilegedActionRegistry:
    """Runs only explicitly registered root-capable actions."""

    def __init__(self) -> None:
        self._handlers: dict[str, PrivilegedActionHandler] = {}

    def register(self, name: str, handler: PrivilegedActionHandler) -> None:
        if name in self._handlers:
            raise ValueError(f"Privileged action is already registered: {name}")
        self._handlers[name] = handler

    def list_actions(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    def run(
        self,
        name: str,
        payload: dict[str, Any] | None = None,
        *,
        runtime: Any | None = None,
    ) -> PrivilegedActionResult:
        handler = self._handlers.get(name)
        if handler is None:
            raise KeyError(name)
        action_payload = payload or {}
        if not isinstance(action_payload, dict):
            raise PrivilegedActionError("Privileged action payload must be a JSON object.")
        return PrivilegedActionResult(
            action=name,
            data=handler(action_payload, runtime or get_runtime()),
        )


def create_builtin_privileged_action_registry() -> PrivilegedActionRegistry:
    from simple_safer_server.core.privileged_job_actions import (
        run_cloud_backup_sync_action,
        run_ddns_update_action,
        run_drive_health_page_check_action,
        run_drive_health_refresh_summary_action,
        run_drive_health_scheduled_check_action,
        run_file_sharing_reload_action,
        run_file_sharing_remove_user_action,
        run_file_sharing_sync_user_action,
        run_file_sharing_write_shares_action,
        run_storage_format_action,
        run_storage_managed_drive_action,
        run_storage_managed_unmount_action,
        run_storage_mount_action,
        run_storage_mount_check_action,
        run_storage_safety_check_action,
        run_storage_unmount_action,
        run_system_poweroff_action,
        run_system_reboot_action,
    )
    from simple_safer_server.modules.alerts.privileged import write_smtp_config_action
    from simple_safer_server.modules.cloud_backup.privileged import write_rclone_config_action

    registry = PrivilegedActionRegistry()
    registry.register("alerts.write-smtp-config", write_smtp_config_action)
    registry.register("cloud-backup.sync", run_cloud_backup_sync_action)
    registry.register("cloud-backup.write-rclone-config", write_rclone_config_action)
    registry.register("ddns.update", run_ddns_update_action)
    registry.register("drive-health.page-check", run_drive_health_page_check_action)
    registry.register("drive-health.refresh-summary", run_drive_health_refresh_summary_action)
    registry.register("drive-health.scheduled-check", run_drive_health_scheduled_check_action)
    registry.register("file-sharing.reload", run_file_sharing_reload_action)
    registry.register("file-sharing.remove-user", run_file_sharing_remove_user_action)
    registry.register("file-sharing.sync-user", run_file_sharing_sync_user_action)
    registry.register("file-sharing.write-shares", run_file_sharing_write_shares_action)
    registry.register("storage.format", run_storage_format_action)
    registry.register("storage.mount", run_storage_mount_action)
    registry.register("storage.mount-check", run_storage_mount_check_action)
    registry.register("storage.managed-drive", run_storage_managed_drive_action)
    registry.register("storage.managed-unmount", run_storage_managed_unmount_action)
    registry.register("storage.safety-check", run_storage_safety_check_action)
    registry.register("storage.unmount", run_storage_unmount_action)
    registry.register("system.poweroff", run_system_poweroff_action)
    registry.register("system.reboot", run_system_reboot_action)
    return registry


def read_json_payload(stdin: TextIO) -> dict[str, Any]:
    raw_payload = stdin.read()
    if not raw_payload.strip():
        return {}
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise PrivilegedActionError(f"Invalid JSON payload: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise PrivilegedActionError("Privileged action payload must be a JSON object.")
    return payload
