from typing import Any

import psutil
from flask import Blueprint, current_app

from simple_safer_server.services.backup_drive_setup import (
    BackupDriveSetupError,
    apply_backup_drive_configuration,
    list_available_drives,
    unmount_selected_partition,
)
from simple_safer_server.services.backup_drive_unmount import (
    is_selected_partition_managed_backup_drive,
    unmount_managed_backup_drive,
)
from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_data, json_problem, json_request_data
from simple_safer_server.web.dashboard_messages import build_dashboard_unmount_success_message
from simple_safer_server.web.problems import ConflictProblem, OperationProblem, ValidationProblem

storage = Blueprint("storage_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


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


@storage.route("/unmount", methods=["POST"])
@admin_required
def unmount():
    services = _get_services()
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
    mount_point = services.config_manager.get_value(
        "backup", "mount_point", services.runtime.default_mount_point
    )
    mounted = services.system_utils.is_mounted(mount_point)
    if mounted:
        try:
            disk = psutil.disk_usage(mount_point)
            used_storage = f"{disk.used / (1024**3):.1f}"
            total_storage = f"{disk.total / (1024**3):.1f}"
            storage_usage = f"{disk.percent}%"
        except Exception:
            used_storage = total_storage = storage_usage = None
    else:
        used_storage = total_storage = storage_usage = None
    disk_available = total_storage is not None
    return json_data(
        {
            "mounted": mounted,
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


@storage.route("/api/backup_drive/unmount", methods=["POST"])
@api_admin_required
def api_backup_drive_unmount():
    services = _get_services()
    try:
        data = json_request_data()
        partition = data.get("partition")
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
        result = apply_backup_drive_configuration(
            partition=data.get("partition"),
            mount_point=data.get("mount_point"),
            auto_mount=True,
            config_manager=services.config_manager,
            smb_manager=services.smb_manager,
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
    except Exception as exc:
        current_app.logger.error("Error configuring backup drive: %s", exc)
        return json_problem(OperationProblem("Could not configure the backup drive."))
