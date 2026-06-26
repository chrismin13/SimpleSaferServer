import os
from typing import Any

from simple_safer_server.adapters.command_runner import CalledProcessError
from simple_safer_server.modules.storage.backup_drive_setup import (
    get_managed_fstab_entry_for_mount_point,
    split_uuid_device_lookup,
)
from simple_safer_server.modules.storage.location import (
    MODE_EXISTING_FOLDER,
    get_storage_location,
    storage_status,
)
from simple_safer_server.web.i18n import gettext
from simple_safer_server.web.problems import OperationProblem, ValidationProblem


class StorageService:
    """Owns dashboard storage actions so routes stay HTTP-only."""

    def __init__(
        self,
        runtime: Any,
        fake_state: Any,
        config_manager: Any,
        command_adapter: Any,
        system_utils: Any,
        command_runner: Any,
    ) -> None:
        self._runtime = runtime
        self._fake_state = fake_state
        self._config_manager = config_manager
        self._command_adapter = command_adapter
        self._system_utils = system_utils
        self._command_runner = command_runner

    def mount_dashboard_drive(self) -> str:
        location = get_storage_location(self._config_manager, runtime=self._runtime)
        if location.mode == MODE_EXISTING_FOLDER:
            status = storage_status(
                self._config_manager,
                self._system_utils,
                runtime=self._runtime,
                command_runner=self._command_runner,
            )
            if not status["ok"]:
                raise ValidationProblem(status["error"], slug="storage-validation-error")
            return gettext("Storage folder is available.")

        mount_point = self._config_manager.get_value(
            "backup", "mount_point", self._runtime.default_mount_point
        )
        if not mount_point:
            raise ValidationProblem(
                gettext("No mount point configured."),
                slug="storage-validation-error",
            )
        uuid = self._config_manager.get_value("backup", "uuid", None)
        if self._runtime.is_fake:
            if not os.path.isdir(mount_point):
                raise ValidationProblem(
                    gettext("Source folder not found: {mount_point}").format(
                        mount_point=mount_point
                    ),
                    slug="storage-validation-error",
                )
            self._fake_state.set_mount(True, mount_point=mount_point)
            self._fake_state.append_task_log(
                "Check Mount", f"Backup source connected at {mount_point}."
            )
            return gettext("Local backup source connected.")

        if not uuid:
            raise ValidationProblem(
                gettext("No drive UUID configured."),
                slug="storage-validation-error",
            )

        try:
            matching_devices = split_uuid_device_lookup(
                self._command_adapter.find_device_by_uuid(uuid)
            )
            if not matching_devices:
                raise ValidationProblem(
                    gettext("Drive not found. Please check the connection."),
                    slug="storage-validation-error",
                )
            if len(matching_devices) > 1:
                raise ValidationProblem(
                    gettext(
                        "Multiple connected drives have the configured backup drive UUID. "
                        "Disconnect cloned drives or re-run backup drive setup before mounting."
                    ),
                    slug="storage-validation-error",
                )
            partition_device = matching_devices[0]
            os.makedirs(mount_point, exist_ok=True)
            managed_fstab_entry = get_managed_fstab_entry_for_mount_point(
                mount_point, runtime=self._runtime
            )
            if managed_fstab_entry:
                if managed_fstab_entry.get("uuid") != uuid:
                    raise ValidationProblem(
                        gettext(
                            "Managed fstab entry does not match the configured backup drive UUID. "
                            "Re-run managed-drive setup from Storage before mounting."
                        ),
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
                "smbd",
                "nmbd",
            ]:
                self._command_adapter.start_unit(unit_name)
            return gettext("Drive mounted and available for use.")
        except CalledProcessError as exc:
            raise OperationProblem(gettext("Failed to mount drive.")) from exc
        except OSError as exc:
            raise OperationProblem(
                gettext(
                    "Could not create or access the mount point. Check that the configured "
                    "folder path is valid and writable."
                )
            ) from exc
