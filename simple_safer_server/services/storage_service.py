import os
from typing import Any, Dict, Tuple

from simple_safer_server.adapters.command_runner import CalledProcessError


class StorageService:
    """Owns dashboard storage actions so routes stay HTTP-only."""

    def __init__(
        self,
        runtime: Any,
        fake_state: Any,
        config_manager: Any,
        command_adapter: Any,
    ) -> None:
        self._runtime = runtime
        self._fake_state = fake_state
        self._config_manager = config_manager
        self._command_adapter = command_adapter

    def restart_system(self) -> Tuple[Dict[str, Any], int]:
        if self._runtime.is_fake:
            return {"success": True, "message": "Fake mode: restart simulated."}, 200
        try:
            self._command_adapter.reboot()
            return {"success": True, "message": "System is restarting..."}, 200
        except CalledProcessError as exc:
            return {"success": False, "message": f"Failed to restart system: {exc}"}, 500

    def shutdown_system(self) -> Tuple[Dict[str, Any], int]:
        if self._runtime.is_fake:
            return {"success": True, "message": "Fake mode: shutdown simulated."}, 200
        try:
            self._command_adapter.poweroff()
            return {"success": True, "message": "System is shutting down..."}, 200
        except CalledProcessError as exc:
            return {"success": False, "message": f"Failed to shut down system: {exc}"}, 500

    def mount_dashboard_drive(self) -> Tuple[Dict[str, Any], int]:
        mount_point = self._config_manager.get_value(
            "backup", "mount_point", self._runtime.default_mount_point
        )
        if not mount_point:
            return {"success": False, "message": "No mount point configured."}, 400
        uuid = self._config_manager.get_value("backup", "uuid", None)
        if self._runtime.is_fake:
            if not os.path.isdir(mount_point):
                return {
                    "success": False,
                    "message": f"Source folder not found: {mount_point}",
                }, 400
            self._fake_state.set_mount(True, mount_point=mount_point)
            self._fake_state.append_task_log(
                "Check Mount", f"Backup source connected at {mount_point}."
            )
            return {"success": True, "message": "Local backup source connected."}, 200

        if not uuid:
            return {"success": False, "message": "No drive UUID configured."}, 400

        try:
            partition_device = self._command_adapter.find_device_by_uuid(uuid)
            if not partition_device:
                return {
                    "success": False,
                    "message": "Drive not found. Please check the connection.",
                }, 400
            os.makedirs(mount_point, exist_ok=True)
            self._command_adapter.mount(partition_device, mount_point)
            # Start mount-dependent checks/backups only after the volume exists;
            # smbd/nmbd expose Samba shares after the mounted paths are available.
            for unit_name in [
                "check_mount.service",
                "check_health.service",
                "backup_cloud.service",
                "smbd",
                "nmbd",
            ]:
                self._command_adapter.start_unit(unit_name)
            return {"success": True, "message": "Drive mounted and available for use."}, 200
        except CalledProcessError as exc:
            return {"success": False, "message": f"Failed to mount drive: {exc}"}, 500
        except OSError:
            return {
                "success": False,
                "message": (
                    "Could not prepare the mount point. Check that the configured "
                    "folder path is valid and writable."
                ),
            }, 500
