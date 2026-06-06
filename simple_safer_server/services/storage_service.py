import os
from typing import Any

from simple_safer_server.adapters.command_runner import CalledProcessError
from simple_safer_server.services.backup_drive_setup import get_managed_fstab_entry_for_mount_point
from simple_safer_server.web.problems import OperationProblem, ValidationProblem


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

    def restart_system(self) -> str:
        if self._runtime.is_fake:
            return "Fake mode: restart simulated."
        try:
            self._command_adapter.reboot()
            return "System is restarting..."
        except CalledProcessError as exc:
            raise OperationProblem("Failed to restart system.") from exc

    def shutdown_system(self) -> str:
        if self._runtime.is_fake:
            return "Fake mode: shutdown simulated."
        try:
            self._command_adapter.poweroff()
            return "System is shutting down..."
        except CalledProcessError as exc:
            raise OperationProblem("Failed to shut down system.") from exc

    def mount_dashboard_drive(self) -> str:
        mount_point = self._config_manager.get_value(
            "backup", "mount_point", self._runtime.default_mount_point
        )
        if not mount_point:
            raise ValidationProblem("No mount point configured.", slug="storage-validation-error")
        uuid = self._config_manager.get_value("backup", "uuid", None)
        if self._runtime.is_fake:
            if not os.path.isdir(mount_point):
                raise ValidationProblem(
                    f"Source folder not found: {mount_point}", slug="storage-validation-error"
                )
            self._fake_state.set_mount(True, mount_point=mount_point)
            self._fake_state.append_task_log(
                "Check Mount", f"Backup source connected at {mount_point}."
            )
            return "Local backup source connected."

        if not uuid:
            raise ValidationProblem("No drive UUID configured.", slug="storage-validation-error")

        try:
            partition_device = self._command_adapter.find_device_by_uuid(uuid)
            if not partition_device:
                raise ValidationProblem(
                    "Drive not found. Please check the connection.",
                    slug="storage-validation-error",
                )
            os.makedirs(mount_point, exist_ok=True)
            managed_fstab_entry = get_managed_fstab_entry_for_mount_point(
                mount_point, runtime=self._runtime
            )
            if managed_fstab_entry:
                if managed_fstab_entry.get("uuid") != uuid:
                    raise ValidationProblem(
                        "Managed fstab entry does not match the configured backup drive UUID. "
                        "Re-run backup drive setup from Drive Health before mounting.",
                        slug="storage-validation-error",
                    )
                # Prefer the managed fstab entry only after the UUID matches so
                # remounts keep the admin-selected NTFS driver without letting a
                # stale fstab line mount a different backup disk.
                self._command_adapter.mount_managed(mount_point)
            else:
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
            return "Drive mounted and available for use."
        except CalledProcessError as exc:
            raise OperationProblem("Failed to mount drive.") from exc
        except OSError as exc:
            raise OperationProblem(
                "Could not prepare the mount point. Check that the configured "
                "folder path is valid and writable."
            ) from exc
