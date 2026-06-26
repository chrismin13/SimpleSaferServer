from __future__ import annotations

from pathlib import Path
from typing import Any

from simple_safer_server.adapters.command_runner import CalledProcessError, CommandRunner
from simple_safer_server.adapters.storage_commands import StorageCommandAdapter
from simple_safer_server.core.ownership import record_runtime_owned_resource
from simple_safer_server.core.privileged_actions import PrivilegedActionError
from simple_safer_server.modules.drive_health.service import (
    build_drive_health_page_result,
    build_drive_health_summary,
)
from simple_safer_server.modules.file_sharing.samba_layout import (
    SSS_GLOBALS_FILENAME,
    SSS_SHARES_FILENAME,
)
from simple_safer_server.modules.file_sharing.service import SMBManager
from simple_safer_server.modules.storage.backup_drive_setup import (
    DEFAULT_NTFS_DRIVER,
    FSTAB_MARKER,
    BackupDriveSetupError,
    format_backup_drive,
    unmount_disk_partitions,
    unmount_selected_partition,
)
from simple_safer_server.modules.storage.backup_drive_unmount import (
    is_selected_partition_managed_backup_drive,
    unmount_managed_backup_drive,
)
from simple_safer_server.modules.storage.location import (
    StorageLocationError,
    configure_managed_drive_storage,
    marker_path,
    validate_storage_ready_for_backup,
)
from simple_safer_server.modules.storage.service import StorageService
from simple_safer_server.services.config_manager import ConfigManager
from simple_safer_server.services.runtime import get_fake_state
from simple_safer_server.services.system_utils import SystemUtils
from simple_safer_server.services.user_manager import (
    VALID_USERNAME_RE,
    remove_samba_account,
    sync_user_to_samba_account,
)
from simple_safer_server.web.problems import OperationProblem, ValidationProblem

_MANAGED_DRIVE_PAYLOAD_FIELDS = frozenset({"partition", "mount_point", "ntfs_driver"})
_MANAGED_UNMOUNT_PAYLOAD_FIELDS = frozenset({"power_down"})
_STORAGE_FORMAT_PAYLOAD_FIELDS = frozenset({"disk"})
_STORAGE_UNMOUNT_PAYLOAD_FIELDS = frozenset({"disk", "partition", "force_managed"})
_FILE_SHARING_WRITE_SHARES_PAYLOAD_FIELDS = frozenset({"shares_config"})
_FILE_SHARING_SYNC_USER_PAYLOAD_FIELDS = frozenset({"username", "password"})
_FILE_SHARING_REMOVE_USER_PAYLOAD_FIELDS = frozenset({"username"})


def _reject_payload(payload: dict[str, Any]) -> None:
    if payload:
        raise PrivilegedActionError("This privileged action does not accept payload fields.")


def _reject_unknown_payload_fields(payload: dict[str, Any], allowed: frozenset[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise PrivilegedActionError(
            f"Unsupported privileged action payload field: {', '.join(unknown)}"
        )


def _payload_text(
    payload: dict[str, Any],
    field: str,
    *,
    required: bool = False,
    default: str = "",
) -> str:
    value = payload.get(field, default)
    if required and field not in payload:
        raise PrivilegedActionError(f"Missing required privileged action payload field: {field}")
    if not isinstance(value, str):
        raise PrivilegedActionError(f"Privileged action payload field must be text: {field}")
    value = value.strip()
    if required and not value:
        raise PrivilegedActionError(f"Privileged action payload field cannot be empty: {field}")
    return value


def _payload_bool(payload: dict[str, Any], field: str, *, default: bool) -> bool:
    value = payload.get(field, default)
    if not isinstance(value, bool):
        raise PrivilegedActionError(f"Privileged action payload field must be true or false: {field}")
    return value


def _payload_username(payload: dict[str, Any]) -> str:
    username = _payload_text(payload, "username", required=True)
    if not VALID_USERNAME_RE.match(username):
        raise PrivilegedActionError(
            "Username may only contain letters, numbers, underscores, and hyphens."
        )
    return username


def _payload_password(payload: dict[str, Any]) -> str:
    password = payload.get("password")
    if not isinstance(password, str) or not password:
        raise PrivilegedActionError("password is required.")
    if "\x00" in password or "\n" in password or "\r" in password:
        raise PrivilegedActionError("password cannot contain line breaks or NUL bytes.")
    return password


def run_worker_job_action(job_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    _reject_payload(payload)
    direct_jobs = _direct_worker_jobs()
    handler = direct_jobs.get(job_name)
    if handler is None:
        raise PrivilegedActionError(f"Privileged worker job is not allowlisted: {job_name}")

    exit_code = int(handler() or 0)
    if exit_code != 0:
        raise PrivilegedActionError(f"Job failed with exit code {exit_code}.")
    return {"job": job_name, "message": "Job completed successfully."}


def _direct_worker_jobs():
    from simple_safer_server.modules.cloud_backup.runner import run_backup_job_direct
    from simple_safer_server.modules.ddns.runner import run_update_job_direct
    from simple_safer_server.modules.drive_health.runner import run_drive_health_job_direct
    from simple_safer_server.modules.storage.runner import run_mount_check_job_direct

    return {
        "cloud-backup": run_backup_job_direct,
        "ddns-update": run_update_job_direct,
        "drive-health": run_drive_health_job_direct,
        "mount-check": run_mount_check_job_direct,
    }


def run_cloud_backup_sync_action(payload: dict[str, Any], runtime: Any) -> dict[str, Any]:
    del runtime
    return run_worker_job_action("cloud-backup", payload)


def run_ddns_update_action(payload: dict[str, Any], runtime: Any) -> dict[str, Any]:
    del runtime
    return run_worker_job_action("ddns-update", payload)


def run_drive_health_page_check_action(
    payload: dict[str, Any],
    runtime: Any,
) -> dict[str, Any]:
    _reject_payload(payload)
    return build_drive_health_page_result(
        ConfigManager(runtime=runtime),
        SystemUtils(runtime=runtime),
        runtime=runtime,
    )


def run_drive_health_refresh_summary_action(
    payload: dict[str, Any],
    runtime: Any,
) -> dict[str, Any]:
    _reject_payload(payload)
    return {
        "summary": build_drive_health_summary(
            ConfigManager(runtime=runtime),
            SystemUtils(runtime=runtime),
            runtime=runtime,
        )
    }


def run_drive_health_scheduled_check_action(payload: dict[str, Any], runtime: Any) -> dict[str, Any]:
    del runtime
    return run_worker_job_action("drive-health", payload)


def run_storage_mount_check_action(payload: dict[str, Any], runtime: Any) -> dict[str, Any]:
    del runtime
    return run_worker_job_action("mount-check", payload)


def run_file_sharing_reload_action(payload: dict[str, Any], runtime: Any) -> dict[str, Any]:
    _reject_payload(payload)
    if not SMBManager(runtime=runtime).restart_services():
        raise PrivilegedActionError("File sharing services did not reload cleanly.")
    return {"message": "File sharing services reloaded."}


def run_file_sharing_write_shares_action(
    payload: dict[str, Any],
    runtime: Any,
) -> dict[str, Any]:
    _reject_unknown_payload_fields(payload, _FILE_SHARING_WRITE_SHARES_PAYLOAD_FIELDS)
    shares_config = payload.get("shares_config")
    if not isinstance(shares_config, str):
        raise PrivilegedActionError("shares_config is required.")
    if "\x00" in shares_config:
        raise PrivilegedActionError("shares_config cannot contain NUL bytes.")

    SMBManager(runtime=runtime).publish_managed_shares(shares_config)
    record_runtime_owned_resource(
        runtime,
        "file-sharing",
        kind="config-file",
        identifier=str(runtime.samba_dir / SSS_GLOBALS_FILENAME),
        reason="Store SSS-owned Samba global settings separately.",
    )
    record_runtime_owned_resource(
        runtime,
        "file-sharing",
        kind="config-file",
        identifier=str(runtime.samba_dir / SSS_SHARES_FILENAME),
        reason="Store only SSS-managed share sections.",
    )
    return {"message": "File sharing shares file published."}


def run_file_sharing_sync_user_action(
    payload: dict[str, Any],
    runtime: Any,
) -> dict[str, Any]:
    _reject_unknown_payload_fields(payload, _FILE_SHARING_SYNC_USER_PAYLOAD_FIELDS)
    username = _payload_username(payload)
    password = _payload_password(payload)
    if not sync_user_to_samba_account(username, password, runtime=runtime):
        raise PrivilegedActionError("Samba user sync failed.")
    return {"username": username, "message": "Samba user synced."}


def run_file_sharing_remove_user_action(
    payload: dict[str, Any],
    runtime: Any,
) -> dict[str, Any]:
    _reject_unknown_payload_fields(payload, _FILE_SHARING_REMOVE_USER_PAYLOAD_FIELDS)
    username = _payload_username(payload)
    if not remove_samba_account(username, runtime=runtime):
        raise PrivilegedActionError("Samba user removal failed.")
    return {"username": username, "message": "Samba user removed."}


def run_storage_safety_check_action(payload: dict[str, Any], runtime: Any) -> dict[str, Any]:
    _reject_payload(payload)
    try:
        location = validate_storage_ready_for_backup(
            ConfigManager(runtime=runtime),
            SystemUtils(runtime=runtime),
            runtime=runtime,
        )
    except StorageLocationError as exc:
        raise PrivilegedActionError(str(exc)) from exc
    return {
        "mode": location.mode,
        "path": location.path,
    }


def run_storage_mount_action(payload: dict[str, Any], runtime: Any) -> dict[str, Any]:
    _reject_payload(payload)
    command_runner = CommandRunner()
    try:
        message = StorageService(
            runtime=runtime,
            fake_state=get_fake_state(runtime) if runtime.is_fake else None,
            config_manager=ConfigManager(runtime=runtime),
            command_adapter=StorageCommandAdapter(command_runner),
            system_utils=SystemUtils(runtime=runtime, command_runner=command_runner),
            command_runner=command_runner,
        ).mount_dashboard_drive()
    except (OperationProblem, ValidationProblem) as exc:
        raise PrivilegedActionError(getattr(exc, "detail", str(exc))) from exc
    return {"message": message}


def _managed_fstab_record_identifier(runtime: Any) -> str:
    fstab_path = Path(runtime.data_dir) / "fstab" if getattr(runtime, "is_fake", False) else Path("/etc/fstab")
    marker = FSTAB_MARKER[1:].strip() if FSTAB_MARKER.startswith("#") else FSTAB_MARKER.strip()
    return f"{fstab_path}#{marker}"


def _record_storage_managed_drive_writes(runtime: Any, mount_point: str) -> None:
    # The module plan records the durable ownership shape. These exact records
    # prove what the root helper wrote on this host after setup succeeded.
    record_runtime_owned_resource(
        runtime,
        "storage",
        kind="marker-file",
        identifier=str(marker_path(mount_point)),
        reason="Confirm cloud backup is reading the intended storage location.",
    )
    record_runtime_owned_resource(
        runtime,
        "storage",
        kind="fstab-entry",
        identifier=_managed_fstab_record_identifier(runtime),
        reason="Mount only the explicitly managed backup drive.",
    )


def run_storage_managed_drive_action(payload: dict[str, Any], runtime: Any) -> dict[str, Any]:
    _reject_unknown_payload_fields(payload, _MANAGED_DRIVE_PAYLOAD_FIELDS)
    partition = _payload_text(payload, "partition", required=True)
    mount_point = _payload_text(
        payload,
        "mount_point",
        default=str(runtime.default_mount_point),
    )
    ntfs_driver = _payload_text(payload, "ntfs_driver", default=DEFAULT_NTFS_DRIVER)

    try:
        result = configure_managed_drive_storage(
            partition=partition,
            mount_point=mount_point,
            config_manager=ConfigManager(runtime=runtime),
            smb_manager=SMBManager(runtime=runtime),
            system_utils=SystemUtils(runtime=runtime),
            runtime=runtime,
            ntfs_driver=ntfs_driver,
        )
    except (BackupDriveSetupError, StorageLocationError, OperationProblem) as exc:
        raise PrivilegedActionError(getattr(exc, "detail", str(exc))) from exc

    result_mount_point = result.get("mount_point", mount_point)
    _record_storage_managed_drive_writes(runtime, result_mount_point)
    return {
        "message": result.get("message", "Managed drive configured."),
        "mount_point": result_mount_point,
        "uuid": result.get("uuid", ""),
        "usb_id": result.get("usb_id", ""),
        "ntfs_driver": result.get("ntfs_driver", ntfs_driver),
    }


def run_storage_format_action(payload: dict[str, Any], runtime: Any) -> dict[str, Any]:
    _reject_unknown_payload_fields(payload, _STORAGE_FORMAT_PAYLOAD_FIELDS)
    disk = _payload_text(payload, "disk", required=True)
    try:
        return format_backup_drive(disk, runtime=runtime)
    except BackupDriveSetupError as exc:
        raise PrivilegedActionError(getattr(exc, "details", "") or str(exc)) from exc


def run_storage_managed_unmount_action(payload: dict[str, Any], runtime: Any) -> dict[str, Any]:
    _reject_unknown_payload_fields(payload, _MANAGED_UNMOUNT_PAYLOAD_FIELDS)
    power_down = _payload_bool(payload, "power_down", default=False)
    config_manager = ConfigManager(runtime=runtime)
    system_utils = SystemUtils(runtime=runtime)
    configured_mount_point = config_manager.get_value(
        "backup", "mount_point", runtime.default_mount_point
    )
    configured_uuid = config_manager.get_value("backup", "uuid", "")
    try:
        unmount_managed_backup_drive(
            configured_mount_point,
            configured_uuid,
            system_utils,
            runtime=runtime,
            power_down=power_down,
        )
    except BackupDriveSetupError as exc:
        raise PrivilegedActionError(getattr(exc, "details", "") or str(exc)) from exc
    return {
        "mount_point": configured_mount_point,
        "uuid": configured_uuid,
        "power_down": power_down,
    }


def run_storage_unmount_action(payload: dict[str, Any], runtime: Any) -> dict[str, Any]:
    _reject_unknown_payload_fields(payload, _STORAGE_UNMOUNT_PAYLOAD_FIELDS)
    disk = _payload_text(payload, "disk")
    partition = _payload_text(payload, "partition")
    force_managed = _payload_bool(payload, "force_managed", default=False)
    config_manager = ConfigManager(runtime=runtime)
    system_utils = SystemUtils(runtime=runtime)

    try:
        if disk:
            return {"message": unmount_disk_partitions(disk, runtime=runtime)}
        if force_managed:
            configured_mount_point = config_manager.get_value(
                "backup", "mount_point", runtime.default_mount_point
            )
            configured_uuid = config_manager.get_value("backup", "uuid", "")
            if not is_selected_partition_managed_backup_drive(
                partition,
                configured_mount_point,
                configured_uuid,
                system_utils,
                runtime=runtime,
            ):
                raise BackupDriveSetupError(
                    "The selected partition is no longer the active configured backup drive."
                )
            unmount_managed_backup_drive(
                configured_mount_point,
                configured_uuid,
                system_utils,
                runtime=runtime,
                power_down=False,
            )
            return {
                "message": (
                    "Drive unmounted after the SMB-safe retry temporarily stopped SMB access "
                    "and related background backup tasks."
                )
            }

        try:
            return {"message": unmount_selected_partition(partition, runtime=runtime)}
        except BackupDriveSetupError as exc:
            if "busy" not in str(exc).lower():
                raise
            configured_mount_point = config_manager.get_value(
                "backup", "mount_point", runtime.default_mount_point
            )
            configured_uuid = config_manager.get_value("backup", "uuid", "")
            if is_selected_partition_managed_backup_drive(
                partition,
                configured_mount_point,
                configured_uuid,
                system_utils,
                runtime=runtime,
            ):
                return {"can_retry_managed_unmount": True}
            raise
    except BackupDriveSetupError as exc:
        raise PrivilegedActionError(getattr(exc, "details", "") or str(exc)) from exc


def run_system_reboot_action(payload: dict[str, Any], runtime: Any) -> dict[str, Any]:
    _reject_payload(payload)
    if runtime.is_fake:
        return {"message": "Fake mode: restart simulated."}
    try:
        StorageCommandAdapter().reboot()
    except CalledProcessError as exc:
        raise PrivilegedActionError("Failed to restart system.") from exc
    return {"message": "System is restarting..."}


def run_system_poweroff_action(payload: dict[str, Any], runtime: Any) -> dict[str, Any]:
    _reject_payload(payload)
    if runtime.is_fake:
        return {"message": "Fake mode: shutdown simulated."}
    try:
        StorageCommandAdapter().poweroff()
    except CalledProcessError as exc:
        raise PrivilegedActionError("Failed to shut down system.") from exc
    return {"message": "System is shutting down..."}
