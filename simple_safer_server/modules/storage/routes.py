from typing import Any

import psutil
from flask import Blueprint, current_app, render_template

from simple_safer_server.core.module_lifecycle import (
    ModuleLifecycleError,
    ownership_manifest_for_runtime,
    require_module_applied,
)
from simple_safer_server.core.ownership import record_runtime_owned_resource
from simple_safer_server.core.privileged_client import PrivilegedActionClientError
from simple_safer_server.modules.file_sharing.module import (
    create_module as create_file_sharing_module,
)
from simple_safer_server.modules.storage.backup_drive_setup import (
    BackupDriveSetupError,
    get_managed_ntfs_driver,
    list_available_drives,
)
from simple_safer_server.modules.storage.location import (
    MODE_EXISTING_FOLDER,
    StorageLocationError,
    get_storage_location,
    marker_path,
    passive_storage_status,
    prepare_existing_folder,
    refresh_storage_task_config,
    repair_storage_marker,
    save_storage_location,
    storage_status,
)
from simple_safer_server.modules.storage.module import create_module as create_storage_module
from simple_safer_server.services.filesystem_browser import list_local_path
from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_data, json_problem, json_request_data
from simple_safer_server.web.dashboard_messages import build_dashboard_unmount_success_message
from simple_safer_server.web.i18n import gettext
from simple_safer_server.web.problems import ConflictProblem, OperationProblem, ValidationProblem

storage = Blueprint("storage_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


def _build_storage_safety_checks(status: dict[str, Any], location: Any) -> list[dict[str, str]]:
    """Translate the backup-source validation result into operator-facing checklist rows."""
    identity_label = (
        "Managed drive UUID match"
        if location.mode != MODE_EXISTING_FOLDER
        else "Folder availability"
    )
    if not status.get("checked", True):
        return [
            {
                "label": "Storage marker file",
                "state": "pending",
                "detail": "Not checked.",
            },
            {
                "label": "Write test",
                "state": "pending",
                "detail": "Not checked.",
            },
            {
                "label": identity_label,
                "state": "pending",
                "detail": "Not checked.",
            },
        ]

    if status.get("ok"):
        identity_detail = (
            "Configured drive matches app config."
            if location.mode != MODE_EXISTING_FOLDER
            else "Folder is writable."
        )
        return [
            {
                "label": "Storage marker file",
                "state": "pass",
                "detail": "Marker matches app config.",
            },
            {"label": "Write test", "state": "pass", "detail": "Last checked just now."},
            {"label": identity_label, "state": "pass", "detail": identity_detail},
            {
                "label": "Folder is writable"
                if location.mode == MODE_EXISTING_FOLDER
                else "Drive is writable",
                "state": "pass",
                "detail": "Folder is writable."
                if location.mode == MODE_EXISTING_FOLDER
                else "Mount is writable.",
            },
            {
                "label": "Test file cycle",
                "state": "pass",
                "detail": "Write, read, and delete succeeded.",
            },
        ]

    error = str(status.get("error") or "Storage checks failed.")
    error_lower = error.lower()
    marker_failed = "marker" in error_lower or "storage id" in error_lower
    write_failed = "write probe" in error_lower or "writable" in error_lower
    identity_failed = not marker_failed and not write_failed

    return [
        {
            "label": "Storage marker file",
            "state": "fail" if marker_failed else "pass",
            "detail": error if marker_failed else "Marker check passed before the later failure.",
        },
        {
            "label": "Write test",
            "state": "fail" if write_failed else ("pending" if marker_failed else "pass"),
            "detail": (
                error
                if write_failed
                else (
                    "Not checked because the marker check failed."
                    if marker_failed
                    else "Write test passed before the later failure."
                )
            ),
        },
        {
            "label": identity_label,
            "state": "fail" if identity_failed else "pending",
            "detail": error if identity_failed else "Not checked until earlier checks pass.",
        },
    ]


def _get_check_mount_next_run() -> Any:
    return _get_services().task_service.get_check_mount_next_run()


def _require_storage_applied():
    services = _get_services()
    try:
        require_module_applied(create_storage_module(), services.runtime)
    except ModuleLifecycleError as exc:
        return json_problem(
            ConflictProblem(
                str(exc),
                title=gettext("Module setup required"),
                slug="module-setup-required",
            )
        )
    return None


def _storage_ui_text() -> dict[str, Any]:
    """Return browser copy used by the Storage overview page script."""
    _ = gettext
    return {
        "checks": {
            "fallbackLabel": _("Check"),
            "passedLine": _("Safety check passed"),
            "passedNote": _("Storage location is ready for cloud backups."),
            "justNow": _("Just now"),
            "failedLine": _("Check failed"),
            "failedNote": _("Storage safety check failed."),
            "failedJustNow": _("Check failed just now"),
        },
        "safety": {
            "success": _("Storage safety check passed."),
            "failure": _("Storage safety check failed."),
            "requestFailure": _("Could not run storage safety check."),
        },
        "repair": {
            "title": _("Repair Storage Marker"),
            "message": _(
                "This recreates the small SimpleSaferServer marker file inside your storage location.\n\n"
                "Cloud backup uses this marker to avoid syncing the wrong or empty folder."
            ),
            "confirm": _("Repair Marker"),
            "success": _("Storage marker repaired."),
            "failure": _("Could not repair storage marker."),
        },
    }


def _storage_change_drive_ui_text() -> dict[str, Any]:
    """Return browser copy used by the managed-drive setup script."""
    _ = gettext
    return {
        "drives": {
            "unknownDrive": _("Unknown Drive"),
            "mountedAt": _("mounted at {mountpoint}"),
            "partitionCount": _("{count} partition(s)"),
            "blankDisk": _("blank"),
            "selectDisk": _("Select a disk..."),
            "noCandidateDisks": _("No candidate disks found"),
            "selectPartition": _("Select an NTFS partition..."),
            "noNtfsPartitions": _("No NTFS partitions found"),
        },
        "status": {
            "refreshingDrives": _("Refreshing drives..."),
            "driveListRefreshed": _("Drive list refreshed."),
            "refreshingPartitions": _("Refreshing partitions..."),
            "partitionListRefreshed": _("Partition list refreshed."),
            "unmountingDisk": _("Unmounting selected disk..."),
            "driveUnmounted": _("Drive unmounted."),
            "formattingDisk": _("Formatting selected disk..."),
            "driveFormatted": _("Drive formatted as NTFS."),
            "unmountingPartition": _("Unmounting selected partition..."),
            "partitionUnmounted": _("Partition unmounted."),
            "applyingDrive": _("Applying managed drive..."),
            "managedDriveSaved": _("Managed drive saved."),
        },
        "errors": {
            "refreshDrivesFailed": _("Failed to refresh drives."),
            "refreshPartitionsFailed": _("Failed to refresh partitions."),
            "selectDiskToUnmount": _("Select a disk to unmount first."),
            "selectDiskToFormat": _("Select a disk to format first."),
            "unmountDiskFailed": _("Failed to unmount the selected disk."),
            "formatDiskFailed": _("Failed to format the selected disk."),
            "selectPartitionToUnmount": _("Select an NTFS partition to unmount first."),
            "unmountPartitionFailed": _("Failed to unmount the selected partition."),
            "selectPartition": _("Select an NTFS partition first."),
            "mountPointRequired": _("Mount point is required."),
            "useDriveFailed": _("Failed to use the selected drive."),
            "noDetails": _("No additional details available."),
        },
        "confirm": {
            "unmountDriveTitle": _("Unmount Drive"),
            "unmountDriveMessage": _(
                "This temporarily unmounts mounted partitions on the selected disk. "
                "It does not change SimpleSaferServer storage configuration."
            ),
            "unmountConfirm": _("Unmount"),
            "formatDriveTitle": _("Format Drive"),
            "formatDriveMessage": _(
                "Formatting {disk} deletes all files and partitions on that disk.\n\n"
                "SimpleSaferServer storage will not change until you use the NTFS partition "
                "in the next section."
            ),
            "formatDriveConfirm": _("Format Drive"),
            "unmountPartitionTitle": _("Unmount Partition"),
            "unmountPartitionMessage": _(
                "This temporarily unmounts the selected partition so it can be used as "
                "the managed drive."
            ),
            "useDriveTitle": _("Use This Drive"),
            "useDriveMessage": _(
                "Use {partition} as SimpleSaferServer storage at {mount_point}?"
            ),
            "useDriveConfirm": _("Use This Drive"),
        },
    }


def _storage_existing_folder_ui_text() -> dict[str, Any]:
    """Return browser copy used by the existing-folder setup script."""
    _ = gettext
    return {
        "messages": {
            "pathRequired": _("Enter a storage folder path."),
            "saving": _("Saving storage folder..."),
            "saved": _("Storage folder saved."),
            "saveFailed": _("Could not save storage folder."),
        },
        "folderPicker": {
            "loading": _("Loading..."),
            "emptyMessage": _("No folders or files in this directory."),
            "loadFailed": _("Could not load folders."),
        },
    }


def _apt_lock_block_response(action: str):
    lock_status = _get_services().system_updates_manager.get_lock_status()
    if not lock_status["locked"]:
        return None
    return json_problem(
        ConflictProblem(
            gettext(
                "System {action} is blocked because apt or dpkg is running. "
                "Wait for System Updates to finish, or use the System Updates page to stop the SimpleSaferServer apt operation."
            ).format(action=action),
            slug="storage-apt-lock-blocked",
            extra={"lock": lock_status},
        )
    )


def _refresh_storage_task_config(services: Any) -> None:
    refresh_storage_task_config(services.config_manager, services.system_utils)


def _record_file_sharing_ownership(services: Any) -> None:
    file_sharing = create_file_sharing_module()
    ownership_manifest_for_runtime(services.runtime).record_module_resources(
        file_sharing.slug,
        file_sharing.owned_resources,
    )


def _record_storage_marker_ownership(services: Any, storage_path: str) -> None:
    record_runtime_owned_resource(
        services.runtime,
        "storage",
        kind="marker-file",
        identifier=str(marker_path(storage_path)),
        reason="Confirm cloud backup is reading the intended storage location.",
    )


def _restore_storage_location_after_failure(
    services: Any, previous_location: Any, admin_username: str
) -> bool:
    restored = True
    try:
        save_storage_location(services.config_manager, previous_location)
    except Exception:
        current_app.logger.exception("Could not restore previous storage location after failure")
        restored = False
    try:
        services.smb_manager.ensure_default_backup_share(previous_location.path, admin_username)
        _record_file_sharing_ownership(services)
    except Exception:
        current_app.logger.exception("Could not restore previous backup share after failure")
        restored = False
    return restored


@storage.route("/unmount", methods=["POST"])
@admin_required
def unmount():
    services = _get_services()
    blocked = _require_storage_applied()
    if blocked:
        return blocked
    location = get_storage_location(services.config_manager, runtime=services.runtime)
    if location.mode == MODE_EXISTING_FOLDER:
        return json_problem(
            ValidationProblem(
                gettext("SimpleSaferServer does not mount or unmount existing-folder storage."),
                slug="storage-validation-error",
            )
        )
    mount_point = services.config_manager.get_value(
        "backup", "mount_point", services.runtime.default_mount_point
    )
    try:
        if services.runtime.is_fake:
            services.fake_state.set_mount(False)
            services.fake_state.append_task_log(
                "Check Mount", f"Backup source disconnected from {mount_point}."
            )
            return json_data(
                {},
                message=build_dashboard_unmount_success_message(
                    gettext("Local backup source disconnected."),
                    _get_check_mount_next_run(),
                    availability_phrase=gettext("stays available"),
                    remount_verb=gettext("reconnect"),
                ),
            )

        services.privileged_actions.run("storage.managed-unmount", {"power_down": True})
        return json_data(
            {},
            message=build_dashboard_unmount_success_message(
                gettext("Drive unmounted and powered down. It is now safe to remove the drive."),
                _get_check_mount_next_run(),
            ),
        )
    except PrivilegedActionClientError as exc:
        if exc.exit_code == 2:
            return json_problem(ValidationProblem(str(exc), slug="storage-validation-error"))
        current_app.logger.error("Privileged dashboard unmount action failed: %s", exc)
        return json_problem(
            OperationProblem(gettext("Could not unmount the drive. Check the app logs."))
        )
    except Exception:
        current_app.logger.exception("Unexpected error while unmounting dashboard drive")
        return json_problem(
            OperationProblem(gettext("Could not unmount the drive. Check the app logs."))
        )


@storage.route("/restart", methods=["POST"])
@admin_required
def restart():
    services = _get_services()
    try:
        blocked = _require_storage_applied()
        if blocked:
            return blocked
        blocked = _apt_lock_block_response("restart")
        if blocked:
            return blocked
        result = services.privileged_actions.run("system.reboot", {})
        return json_data({}, message=result.data.get("message", gettext("System is restarting...")))
    except (ValidationProblem, OperationProblem) as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Unexpected error while restarting system")
        return json_problem(
            OperationProblem(
                gettext("Could not restart the system. Check the app logs or systemd journal.")
            )
        )


@storage.route("/shutdown", methods=["POST"])
@admin_required
def shutdown():
    services = _get_services()
    try:
        blocked = _require_storage_applied()
        if blocked:
            return blocked
        blocked = _apt_lock_block_response("shutdown")
        if blocked:
            return blocked
        result = services.privileged_actions.run("system.poweroff", {})
        return json_data(
            {},
            message=result.data.get("message", gettext("System is shutting down...")),
        )
    except (ValidationProblem, OperationProblem) as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Unexpected error while shutting down system")
        return json_problem(
            OperationProblem(
                gettext("Could not shut down the system. Check the app logs or systemd journal.")
            )
        )


@storage.route("/api/storage/status")
@api_admin_required
def api_storage_status():
    services = _get_services()
    location = get_storage_location(services.config_manager, runtime=services.runtime)
    mount_point = location.path
    mounted = services.system_utils.is_mounted(mount_point) if location.app_manages_mount else False
    status = passive_storage_status(
        services.config_manager,
        services.system_utils,
        runtime=services.runtime,
    )
    storage_error = status["error"]
    try:
        # Usage only needs the path to be readable. The stricter available/error
        # fields avoid marker/probe I/O so opening the dashboard does not wake
        # drives just to prove cloud-backup safety.
        disk = psutil.disk_usage(mount_point)
        used_storage = f"{disk.used / (1024**3):.1f}"
        total_storage = f"{disk.total / (1024**3):.1f}"
        storage_usage = f"{disk.percent}%"
    except OSError:
        used_storage = total_storage = storage_usage = None
    disk_available = total_storage is not None
    available = bool(status["ok"] and (disk_available if not location.app_manages_mount else True))
    if not available and not storage_error and not location.app_manages_mount:
        storage_error = gettext("Storage path is not readable.")
    return json_data(
        {
            "mounted": mounted,
            "mode": location.mode,
            "app_manages_mount": location.app_manages_mount,
            "available": available,
            "error": storage_error,
            "disk_available": disk_available,
            "used_storage": used_storage,
            "total_storage": total_storage,
            "storage_usage": storage_usage,
            "mount_point": mount_point,
        }
    )


@storage.route("/mount", methods=["POST"])
@admin_required
def dashboard_mount_drive():
    services = _get_services()
    try:
        blocked = _require_storage_applied()
        if blocked:
            return blocked
        if services.runtime.is_fake:
            message = services.storage_service.mount_dashboard_drive()
        else:
            result = services.privileged_actions.run("storage.mount", {})
            message = result.data.get(
                "message",
                gettext("Drive mounted and available for use."),
            )
        return json_data({}, message=message)
    except PrivilegedActionClientError as exc:
        return json_problem(OperationProblem(str(exc), slug="storage-operation-failed"))
    except (ValidationProblem, OperationProblem) as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Unexpected error while mounting dashboard drive")
        return json_problem(
            OperationProblem(gettext("Could not mount the drive. Check the app logs."))
        )


@storage.route("/api/system/resources")
@api_admin_required
def api_system_resources():
    try:
        cpu_percent = psutil.cpu_percent(interval=0.2)
        ram_percent = psutil.virtual_memory().percent
        net = psutil.net_io_counters()
        return json_data(
            {
                "cpu_usage": cpu_percent,
                "ram_usage": ram_percent,
                "bytes_sent": net.bytes_sent,
                "bytes_recv": net.bytes_recv,
            }
        )
    except Exception:
        current_app.logger.exception("Error reading system resources")
        return json_problem(OperationProblem(gettext("Failed to read system resources.")))


@storage.route("/api/backup_drive/drives", methods=["GET"])
@api_admin_required
def api_backup_drive_drives():
    services = _get_services()
    try:
        return json_data(
            {"drives": list_available_drives(runtime=services.runtime, ntfs_only=True)}
        )
    except Exception as exc:
        current_app.logger.error("Error listing backup drives: %s", exc)
        return json_problem(OperationProblem(str(exc), slug="backup-drive-operation-failed"))


@storage.route("/api/backup_drive/format-drives", methods=["GET"])
@api_admin_required
def api_backup_drive_format_drives():
    services = _get_services()
    try:
        # Formatting is intentionally broader than the NTFS partition picker:
        # admins need to see blank or non-NTFS disks before setting them up.
        return json_data(
            {"drives": list_available_drives(runtime=services.runtime, ntfs_only=False)}
        )
    except Exception as exc:
        current_app.logger.error("Error listing backup format drives: %s", exc)
        return json_problem(OperationProblem(str(exc), slug="backup-drive-operation-failed"))


@storage.route("/api/backup_drive/format", methods=["POST"])
@api_admin_required
def api_backup_drive_format():
    services = _get_services()
    try:
        blocked = _require_storage_applied()
        if blocked:
            return blocked
        data = json_request_data()
        disk = data.get("disk")
        if not disk:
            return json_problem(
                ValidationProblem(
                    gettext("No disk selected."),
                    slug="backup-drive-validation-error",
                )
            )
        # Formatting sets up removable media only; storage config is changed
        # later by /api/backup_drive/configure after the NTFS partition mounts.
        result = services.privileged_actions.run("storage.format", {"disk": disk}).data
        return json_data({"result": result}, message=result["message"])
    except BackupDriveSetupError as exc:
        return json_problem(
            ValidationProblem(
                str(exc),
                slug="backup-drive-validation-error",
                extra={"details": exc.details},
            )
        )
    except PrivilegedActionClientError as exc:
        if exc.exit_code == 2:
            return json_problem(ValidationProblem(str(exc), slug="backup-drive-validation-error"))
        current_app.logger.error("Privileged backup drive format action failed: %s", exc)
        return json_problem(OperationProblem(gettext("Could not format the selected drive.")))
    except Exception as exc:
        current_app.logger.error("Error formatting backup drive: %s", exc)
        return json_problem(OperationProblem(gettext("Could not format the selected drive.")))


@storage.route("/api/backup_drive/unmount", methods=["POST"])
@api_admin_required
def api_backup_drive_unmount():
    services = _get_services()
    try:
        blocked = _require_storage_applied()
        if blocked:
            return blocked
        data = json_request_data()
        partition = data.get("partition")
        disk = data.get("disk")
        result = services.privileged_actions.run(
            "storage.unmount",
            {
                "disk": disk or "",
                "partition": partition or "",
                "force_managed": False,
            },
        )
        if result.data.get("can_retry_managed_unmount"):
            result = services.privileged_actions.run(
                "storage.unmount",
                {
                    "disk": "",
                    "partition": partition or "",
                    "force_managed": True,
                },
            )
            message = build_dashboard_unmount_success_message(
                "Configured backup drive unmounted so backup drive setup can continue.",
                _get_check_mount_next_run(),
            )
        else:
            message = result.data.get("message", gettext("Drive unmounted."))
        return json_data({}, message=message)
    except PrivilegedActionClientError as exc:
        if exc.exit_code == 2:
            return json_problem(ValidationProblem(str(exc), slug="backup-drive-validation-error"))
        current_app.logger.error("Privileged backup drive unmount action failed: %s", exc)
        return json_problem(OperationProblem(gettext("Could not unmount the selected drive.")))
    except BackupDriveSetupError as exc:
        return json_problem(
            ValidationProblem(
                str(exc),
                slug="backup-drive-validation-error",
                extra={"details": exc.details},
            )
        )
    except Exception as exc:
        current_app.logger.error("Error unmounting backup drive: %s", exc)
        return json_problem(OperationProblem(gettext("Could not unmount the selected drive.")))


@storage.route("/api/backup_drive/configure", methods=["POST"])
@api_admin_required
def api_backup_drive_configure():
    services = _get_services()
    try:
        blocked = _require_storage_applied()
        if blocked:
            return blocked
        data = json_request_data()
        result = services.privileged_actions.run(
            "storage.managed-drive",
            {
                "partition": data.get("partition", ""),
                "mount_point": data.get("mount_point", services.runtime.default_mount_point),
                "ntfs_driver": data.get("ntfs_driver", "ntfs-3g"),
            },
        )
        return json_data({"result": result.data})
    except BackupDriveSetupError as exc:
        return json_problem(
            ValidationProblem(
                str(exc),
                slug="backup-drive-validation-error",
                extra={"details": exc.details},
            )
        )
    except OperationProblem as exc:
        return json_problem(exc)
    except PrivilegedActionClientError as exc:
        if exc.exit_code == 2:
            return json_problem(ValidationProblem(str(exc), slug="backup-drive-validation-error"))
        current_app.logger.error("Privileged backup drive action failed: %s", exc)
        return json_problem(OperationProblem(gettext("Could not configure the backup drive.")))
    except Exception as exc:
        current_app.logger.error("Error configuring backup drive: %s", exc)
        return json_problem(OperationProblem(gettext("Could not configure the backup drive.")))


@storage.route("/storage")
@admin_required
def storage_page():
    services = _get_services()
    location = get_storage_location(services.config_manager, runtime=services.runtime)
    drive_config = {
        "mount_point": services.config_manager.get_value(
            "backup", "mount_point", services.runtime.default_mount_point
        ),
        "uuid": services.config_manager.get_value("backup", "uuid", ""),
        "usb_id": services.config_manager.get_value("backup", "usb_id", ""),
        "filesystem": (
            "External"
            if location.mode == MODE_EXISTING_FOLDER
            else get_managed_ntfs_driver(runtime=services.runtime).upper()
        ),
        "last_verified": "Manual check required",
    }
    status = passive_storage_status(
        services.config_manager,
        services.system_utils,
        runtime=services.runtime,
    )
    return render_template(
        "storage.html",
        storage_module=create_storage_module(),
        storage_location=location,
        storage_status=status,
        safety_checks=_build_storage_safety_checks(status, location),
        drive_config=drive_config,
        storage_ui_text=_storage_ui_text(),
    )


@storage.route("/api/storage/safety-check", methods=["POST"])
@api_admin_required
def api_storage_safety_check():
    services = _get_services()
    try:
        blocked = _require_storage_applied()
        if blocked:
            return blocked
        status = storage_status(
            services.config_manager,
            services.system_utils,
            runtime=services.runtime,
            command_runner=services.command_runner,
        )
        status["checked"] = True
        location = status["location"]
        message = (
            gettext("Storage safety check passed.")
            if status["ok"]
            else gettext("Storage safety check failed.")
        )
        return json_data(
            {
                "ok": status["ok"],
                "error": status["error"],
                "safety_checks": _build_storage_safety_checks(status, location),
            },
            message=message,
        )
    except Exception:
        current_app.logger.exception("Could not run storage safety check")
        return json_problem(OperationProblem(gettext("Could not run the storage safety check.")))


@storage.route("/storage/change-drive")
@admin_required
def storage_change_drive_page():
    services = _get_services()
    drive_config = {
        "mount_point": services.config_manager.get_value(
            "backup", "mount_point", services.runtime.default_mount_point
        ),
        "uuid": services.config_manager.get_value("backup", "uuid", ""),
        "usb_id": services.config_manager.get_value("backup", "usb_id", ""),
    }
    return render_template(
        "storage_change_drive.html",
        storage_module=create_storage_module(),
        drive_config=drive_config,
        storage_change_drive_ui_text=_storage_change_drive_ui_text(),
    )


@storage.route("/storage/existing-folder")
@admin_required
def storage_existing_folder_page():
    services = _get_services()
    location = get_storage_location(services.config_manager, runtime=services.runtime)
    current_path = location.path if location.mode == MODE_EXISTING_FOLDER else ""
    return render_template(
        "storage_existing_folder.html",
        storage_module=create_storage_module(),
        current_path=current_path,
        storage_existing_folder_ui_text=_storage_existing_folder_ui_text(),
    )


@storage.route("/api/storage/existing-folder", methods=["POST"])
@api_admin_required
def api_existing_folder():
    services = _get_services()
    storage_saved = False
    previous_location = None
    admin_username = ""
    try:
        blocked = _require_storage_applied()
        if blocked:
            return blocked
        data = json_request_data()
        admin_username = services.config_manager.get_value("system", "username", "")
        previous_location = get_storage_location(
            services.config_manager,
            runtime=services.runtime,
        )
        location = prepare_existing_folder(
            data.get("path", ""),
            runtime=services.runtime,
            command_runner=services.command_runner,
        )
        _record_storage_marker_ownership(services, location.path)
        services.smb_manager.ensure_default_backup_share(
            location.path,
            admin_username,
        )
        _record_file_sharing_ownership(services)
        save_storage_location(services.config_manager, location)
        storage_saved = True
        _refresh_storage_task_config(services)
        return json_data({"path": location.path}, message=gettext("Storage folder saved."))
    except StorageLocationError as exc:
        return json_problem(ValidationProblem(str(exc), slug="storage-validation-error"))
    except OperationProblem as exc:
        if storage_saved and previous_location is not None:
            restored = _restore_storage_location_after_failure(
                services, previous_location, admin_username
            )
            if restored:
                return json_problem(
                    OperationProblem(
                        gettext("{detail} Previous storage settings were restored.").format(
                            detail=exc.detail
                        )
                    )
                )
        return json_problem(exc)
    except Exception:
        if storage_saved and previous_location is not None:
            _restore_storage_location_after_failure(services, previous_location, admin_username)
        current_app.logger.exception("Could not configure existing storage folder")
        return json_problem(OperationProblem(gettext("Could not configure the storage folder.")))


@storage.route("/api/storage/list-path", methods=["POST"])
@api_admin_required
def api_storage_list_path():
    try:
        data = json_request_data()
        return json_data(list_local_path(data.get("path", "/")))
    except NotADirectoryError as exc:
        return json_problem(ValidationProblem(str(exc), slug="storage-validation-error"))
    except OSError:
        current_app.logger.exception("Could not list local storage picker path")
        return json_problem(OperationProblem(gettext("Could not list that folder.")))


@storage.route("/api/storage/repair-marker", methods=["POST"])
@api_admin_required
def api_repair_storage_marker():
    services = _get_services()
    try:
        blocked = _require_storage_applied()
        if blocked:
            return blocked
        location = repair_storage_marker(services.config_manager, runtime=services.runtime)
        _record_storage_marker_ownership(services, location.path)
        return json_data({"path": location.path}, message=gettext("Storage marker repaired."))
    except StorageLocationError as exc:
        return json_problem(ValidationProblem(str(exc), slug="storage-validation-error"))
    except Exception:
        current_app.logger.exception("Could not repair storage marker")
        return json_problem(OperationProblem(gettext("Could not repair the storage marker.")))
