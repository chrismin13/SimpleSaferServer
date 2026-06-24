from typing import Any

import psutil
from flask import Blueprint, current_app, render_template

from simple_safer_server.services.backup_drive_setup import (
    BackupDriveSetupError,
    format_backup_drive,
    get_managed_ntfs_driver,
    list_available_drives,
    unmount_disk_partitions,
    unmount_selected_partition,
)
from simple_safer_server.services.backup_drive_unmount import (
    is_selected_partition_managed_backup_drive,
    unmount_managed_backup_drive,
)
from simple_safer_server.services.filesystem_browser import list_local_path
from simple_safer_server.services.storage_location import (
    MODE_EXISTING_FOLDER,
    StorageLocationError,
    configure_managed_drive_storage,
    get_storage_location,
    passive_storage_status,
    prepare_existing_folder,
    refresh_storage_timers,
    repair_storage_marker,
    save_storage_location,
    storage_status,
)
from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_data, json_problem, json_request_data
from simple_safer_server.web.dashboard_messages import build_dashboard_unmount_success_message
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


def _apt_lock_block_response(action: str):
    lock_status = _get_services().system_updates_manager.get_lock_status()
    if not lock_status["locked"]:
        return None
    return json_problem(
        ConflictProblem(
            (
                f"System {action} is blocked because apt or dpkg is running. "
                "Wait for System Updates to finish, or use the System Updates page to stop the SimpleSaferServer apt operation."
            ),
            slug="storage-apt-lock-blocked",
            extra={"lock": lock_status},
        )
    )


def _refresh_storage_timers(services: Any) -> None:
    refresh_storage_timers(services.config_manager, services.system_utils)


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
    except Exception:
        current_app.logger.exception("Could not restore previous backup share after failure")
        restored = False
    return restored


@storage.route("/unmount", methods=["POST"])
@admin_required
def unmount():
    services = _get_services()
    location = get_storage_location(services.config_manager, runtime=services.runtime)
    if location.mode == MODE_EXISTING_FOLDER:
        return json_problem(
            ValidationProblem(
                "SimpleSaferServer does not mount or unmount existing-folder storage.",
                slug="storage-validation-error",
            )
        )
    mount_point = services.config_manager.get_value(
        "backup", "mount_point", services.runtime.default_mount_point
    )
    configured_uuid = services.config_manager.get_value("backup", "uuid", None)
    try:
        if services.runtime.is_fake:
            services.fake_state.set_mount(False)
            services.fake_state.append_task_log(
                "Check Mount", f"Backup source disconnected from {mount_point}."
            )
            return json_data(
                {},
                message=build_dashboard_unmount_success_message(
                    "Local backup source disconnected.",
                    _get_check_mount_next_run(),
                    availability_phrase="stays available",
                    remount_verb="reconnect",
                ),
            )

        unmount_managed_backup_drive(
            mount_point,
            configured_uuid,
            services.system_utils,
            runtime=services.runtime,
            power_down=True,
        )
        return json_data(
            {},
            message=build_dashboard_unmount_success_message(
                "Drive unmounted and powered down. It is now safe to remove the drive.",
                _get_check_mount_next_run(),
            ),
        )
    except BackupDriveSetupError as exc:
        return json_problem(ValidationProblem(str(exc), slug="storage-validation-error"))
    except Exception:
        current_app.logger.exception("Unexpected error while unmounting dashboard drive")
        return json_problem(OperationProblem("Could not unmount the drive. Check the app logs."))


@storage.route("/restart", methods=["POST"])
@admin_required
def restart():
    services = _get_services()
    try:
        blocked = _apt_lock_block_response("restart")
        if blocked:
            return blocked
        message = services.storage_service.restart_system()
        return json_data({}, message=message)
    except (ValidationProblem, OperationProblem) as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Unexpected error while restarting system")
        return json_problem(
            OperationProblem("Could not restart the system. Check the app logs or systemd journal.")
        )


@storage.route("/shutdown", methods=["POST"])
@admin_required
def shutdown():
    services = _get_services()
    try:
        blocked = _apt_lock_block_response("shutdown")
        if blocked:
            return blocked
        message = services.storage_service.shutdown_system()
        return json_data({}, message=message)
    except (ValidationProblem, OperationProblem) as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Unexpected error while shutting down system")
        return json_problem(
            OperationProblem(
                "Could not shut down the system. Check the app logs or systemd journal."
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
        storage_error = "Storage path is not readable."
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
        message = services.storage_service.mount_dashboard_drive()
        return json_data({}, message=message)
    except (ValidationProblem, OperationProblem) as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Unexpected error while mounting dashboard drive")
        return json_problem(OperationProblem("Could not mount the drive. Check the app logs."))


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
        return json_problem(OperationProblem("Failed to read system resources."))


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
        data = json_request_data()
        # Formatting sets up removable media only; storage config is changed
        # later by /api/backup_drive/configure after the NTFS partition mounts.
        result = format_backup_drive(data.get("disk"), runtime=services.runtime)
        return json_data({"result": result}, message=result["message"])
    except BackupDriveSetupError as exc:
        return json_problem(
            ValidationProblem(
                str(exc),
                slug="backup-drive-validation-error",
                extra={"details": exc.details},
            )
        )
    except Exception as exc:
        current_app.logger.error("Error formatting backup drive: %s", exc)
        return json_problem(OperationProblem("Could not format the selected drive."))


@storage.route("/api/backup_drive/unmount", methods=["POST"])
@api_admin_required
def api_backup_drive_unmount():
    services = _get_services()
    try:
        data = json_request_data()
        partition = data.get("partition")
        disk = data.get("disk")
        if disk:
            # Disk unmount is for the format section. It only clears live mounts
            # and does not deconfigure the current backup source.
            message = unmount_disk_partitions(disk, runtime=services.runtime)
            return json_data({}, message=message)

        configured_mount_point = services.config_manager.get_value(
            "backup",
            "mount_point",
            services.runtime.default_mount_point,
        )
        configured_uuid = services.config_manager.get_value("backup", "uuid", None)

        if is_selected_partition_managed_backup_drive(
            partition,
            configured_mount_point,
            configured_uuid,
            services.system_utils,
            runtime=services.runtime,
        ):
            unmount_managed_backup_drive(
                configured_mount_point,
                configured_uuid,
                services.system_utils,
                runtime=services.runtime,
                power_down=False,
            )
            message = build_dashboard_unmount_success_message(
                "Configured backup drive unmounted so backup drive setup can continue.",
                _get_check_mount_next_run(),
            )
        else:
            message = unmount_selected_partition(partition, runtime=services.runtime)
        return json_data({}, message=message)
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
        return json_problem(OperationProblem("Could not unmount the selected drive."))


@storage.route("/api/backup_drive/configure", methods=["POST"])
@api_admin_required
def api_backup_drive_configure():
    services = _get_services()
    try:
        data = json_request_data()
        result = configure_managed_drive_storage(
            partition=data.get("partition"),
            mount_point=data.get("mount_point"),
            config_manager=services.config_manager,
            smb_manager=services.smb_manager,
            system_utils=services.system_utils,
            runtime=services.runtime,
            ntfs_driver=data.get("ntfs_driver", "ntfs-3g"),
        )
        return json_data({"result": result})
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
    except Exception as exc:
        current_app.logger.error("Error configuring backup drive: %s", exc)
        return json_problem(OperationProblem("Could not configure the backup drive."))


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
        storage_location=location,
        storage_status=status,
        safety_checks=_build_storage_safety_checks(status, location),
        drive_config=drive_config,
    )


@storage.route("/api/storage/safety-check", methods=["POST"])
@api_admin_required
def api_storage_safety_check():
    services = _get_services()
    try:
        status = storage_status(
            services.config_manager,
            services.system_utils,
            runtime=services.runtime,
            command_runner=services.command_runner,
        )
        status["checked"] = True
        location = status["location"]
        message = "Storage safety check passed." if status["ok"] else "Storage safety check failed."
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
        return json_problem(OperationProblem("Could not run the storage safety check."))


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
    return render_template("storage_change_drive.html", drive_config=drive_config)


@storage.route("/storage/existing-folder")
@admin_required
def storage_existing_folder_page():
    services = _get_services()
    location = get_storage_location(services.config_manager, runtime=services.runtime)
    current_path = location.path if location.mode == MODE_EXISTING_FOLDER else ""
    return render_template(
        "storage_existing_folder.html",
        current_path=current_path,
    )


@storage.route("/api/storage/existing-folder", methods=["POST"])
@api_admin_required
def api_existing_folder():
    services = _get_services()
    storage_saved = False
    previous_location = None
    admin_username = ""
    try:
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
        services.smb_manager.ensure_default_backup_share(
            location.path,
            admin_username,
        )
        save_storage_location(services.config_manager, location)
        storage_saved = True
        _refresh_storage_timers(services)
        return json_data({"path": location.path}, message="Storage folder saved.")
    except StorageLocationError as exc:
        return json_problem(ValidationProblem(str(exc), slug="storage-validation-error"))
    except OperationProblem as exc:
        if storage_saved and previous_location is not None:
            restored = _restore_storage_location_after_failure(
                services, previous_location, admin_username
            )
            if restored:
                return json_problem(
                    OperationProblem(f"{exc.detail} Previous storage settings were restored.")
                )
        return json_problem(exc)
    except Exception:
        if storage_saved and previous_location is not None:
            _restore_storage_location_after_failure(services, previous_location, admin_username)
        current_app.logger.exception("Could not configure existing storage folder")
        return json_problem(OperationProblem("Could not configure the storage folder."))


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
        return json_problem(OperationProblem("Could not list that folder."))


@storage.route("/api/storage/repair-marker", methods=["POST"])
@api_admin_required
def api_repair_storage_marker():
    services = _get_services()
    try:
        location = repair_storage_marker(services.config_manager, runtime=services.runtime)
        return json_data({"path": location.path}, message="Storage marker repaired.")
    except StorageLocationError as exc:
        return json_problem(ValidationProblem(str(exc), slug="storage-validation-error"))
    except Exception:
        current_app.logger.exception("Could not repair storage marker")
        return json_problem(OperationProblem("Could not repair the storage marker."))
