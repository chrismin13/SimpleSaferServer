import logging

from simple_safer_server.services.file_persistence import locked_path
from simple_safer_server.services.storage_location import (
    StorageLocationError,
    existing_folder_configuration,
    save_storage_location,
)

LOGGER = logging.getLogger(__name__)


class StorageConfigurationError(Exception):
    """Raised when storage configuration or its recovery could not finish."""


def refresh_storage_timers(config_manager, system_utils):
    config = config_manager.get_all_config()
    ok, error = system_utils.create_systemd_config_file(config)
    if not ok:
        raise StorageConfigurationError(f"Systemd config was not refreshed: {error}")
    ok, error = system_utils.install_systemd_services_and_timers(config)
    if not ok:
        raise StorageConfigurationError(f"Task timers were not refreshed: {error}")


def change_existing_folder(
    path, *, config_manager, smb_manager, system_utils, runtime, command_runner
):
    # Keep two folder-change requests from saving or rolling back over each other.
    # This lock lives with app configuration and is removed with that directory.
    with locked_path(runtime.config_dir / "storage-change.lock", mode=0o600):
        config_manager.load_config()
        return _change_existing_folder(
            path, config_manager, smb_manager, system_utils, runtime, command_runner
        )


def _change_existing_folder(
    path, config_manager, smb_manager, system_utils, runtime, command_runner
):
    previous_share = smb_manager.get_managed_share("backup")
    share_changed = False
    timers_attempted = False
    try:
        with existing_folder_configuration(
            config_manager, path, runtime=runtime, command_runner=command_runner
        ) as location:
            smb_manager.ensure_default_backup_share(
                location.path, config_manager.get_value("system", "username", "")
            )
            share_changed = True
            save_storage_location(config_manager, location)
            timers_attempted = True
            refresh_storage_timers(config_manager, system_utils)
            return location
    except Exception as exc:
        # The context restores the marker and saved storage location first.
        # Restore only this share's path; rebuilding it would lose custom options.
        failures = []
        if share_changed:
            try:
                if previous_share is None:
                    smb_manager.delete_managed_share("backup")
                else:
                    smb_manager.update_managed_share_path("backup", previous_share["path"])
            except Exception:
                LOGGER.exception("Could not restore the backup share after a folder change")
                failures.append("backup share")
        if timers_attempted:
            try:
                refresh_storage_timers(config_manager, system_utils)
            except Exception:
                LOGGER.exception("Could not restore task timers after a folder change")
                failures.append("task timers")
        if failures:
            raise StorageConfigurationError(
                f"{exc} Recovery could not restore {', '.join(failures)}. "
                "Check these settings before running a backup."
            ) from exc
        if isinstance(exc, StorageLocationError):
            raise
        recovery_message = " Previous storage settings were restored." if share_changed else ""
        raise StorageConfigurationError(
            f"Could not save the storage folder: {exc}{recovery_message}"
        ) from exc
