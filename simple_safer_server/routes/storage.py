import os
import subprocess
from typing import Any

import psutil
from flask import Blueprint, current_app, jsonify, request

from backup_drive_setup import (
    BackupDriveSetupError,
    apply_backup_drive_configuration,
    list_available_drives,
    unmount_selected_partition,
)
from backup_drive_unmount import (
    is_selected_partition_managed_backup_drive,
    unmount_managed_backup_drive,
)
from dashboard_messages import build_dashboard_unmount_success_message
from user_manager import admin_required, api_admin_required

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
    return jsonify(
        {
            "success": False,
            "message": (
                f"System {action} is blocked because apt or dpkg is running. "
                "Wait for System Updates to finish, or use the System Updates page to stop the SimpleSaferServer apt operation."
            ),
            "lock": lock_status,
        }
    ), 409


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
            return jsonify(
                {
                    "success": True,
                    "message": build_dashboard_unmount_success_message(
                        "Local backup source disconnected.",
                        _get_check_mount_next_run(),
                        availability_phrase="stays available",
                        remount_verb="reconnect",
                    ),
                }
            )

        unmount_managed_backup_drive(
            mount_point,
            configured_uuid,
            services.system_utils,
            runtime=services.runtime,
            power_down=True,
        )
        return jsonify(
            {
                "success": True,
                "message": build_dashboard_unmount_success_message(
                    "Drive unmounted and powered down. It is now safe to remove the drive.",
                    _get_check_mount_next_run(),
                ),
            }
        )
    except BackupDriveSetupError as exc:
        return jsonify({"success": False, "message": str(exc)}), 500
    except Exception as exc:
        return jsonify({"success": False, "message": f"Unexpected error: {exc}"}), 500


@storage.route("/restart", methods=["POST"])
@admin_required
def restart():
    services = _get_services()
    try:
        blocked = _apt_lock_block_response("restart")
        if blocked:
            return blocked
        if services.runtime.is_fake:
            return jsonify({"success": True, "message": "Fake mode: restart simulated."})
        subprocess.run(["sudo", "systemctl", "reboot"], check=True)
        return jsonify({"success": True, "message": "System is restarting..."})
    except subprocess.CalledProcessError as exc:
        return jsonify({"success": False, "message": f"Failed to restart system: {exc}"}), 500
    except Exception as exc:
        return jsonify({"success": False, "message": f"Unexpected error: {exc}"}), 500


@storage.route("/shutdown", methods=["POST"])
@admin_required
def shutdown():
    services = _get_services()
    try:
        blocked = _apt_lock_block_response("shutdown")
        if blocked:
            return blocked
        if services.runtime.is_fake:
            return jsonify({"success": True, "message": "Fake mode: shutdown simulated."})
        subprocess.run(["sudo", "systemctl", "poweroff"], check=True)
        return jsonify({"success": True, "message": "System is shutting down..."})
    except subprocess.CalledProcessError as exc:
        return jsonify({"success": False, "message": f"Failed to shut down system: {exc}"}), 500
    except Exception as exc:
        return jsonify({"success": False, "message": f"Unexpected error: {exc}"}), 500


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
    return jsonify(
        {
            "mounted": mounted,
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
    mount_point = services.config_manager.get_value(
        "backup", "mount_point", services.runtime.default_mount_point
    )
    uuid = services.config_manager.get_value("backup", "uuid", None)
    try:
        if services.runtime.is_fake:
            if not os.path.isdir(mount_point):
                return jsonify(
                    {"success": False, "message": f"Source folder not found: {mount_point}"}
                ), 400
            services.fake_state.set_mount(True, mount_point=mount_point)
            services.fake_state.append_task_log(
                "Check Mount", f"Backup source connected at {mount_point}."
            )
            return jsonify({"success": True, "message": "Local backup source connected."})

        if not uuid:
            return jsonify({"success": False, "message": "No drive UUID configured."}), 400
        blkid_out = subprocess.run(
            ["blkid", "-t", f"UUID={uuid}", "-o", "device"], capture_output=True, text=True
        )
        partition_device = blkid_out.stdout.strip()
        if not partition_device:
            return jsonify(
                {"success": False, "message": "Drive not found. Please check the connection."}
            ), 400
        os.makedirs(mount_point, exist_ok=True)
        subprocess.run(["sudo", "mount", partition_device, mount_point], check=True)
        for service in ["check_mount.service", "check_health.service", "backup_cloud.service"]:
            subprocess.run(["sudo", "systemctl", "start", service], check=False)
        subprocess.run(["sudo", "systemctl", "start", "smbd"], check=False)
        subprocess.run(["sudo", "systemctl", "start", "nmbd"], check=False)
        return jsonify({"success": True, "message": "Drive mounted and available for use."})
    except subprocess.CalledProcessError as exc:
        return jsonify({"success": False, "message": f"Failed to mount drive: {exc}"}), 500
    except Exception as exc:
        return jsonify({"success": False, "message": f"Unexpected error: {exc}"}), 500


@storage.route("/api/system/resources")
@api_admin_required
def api_system_resources():
    try:
        cpu_percent = psutil.cpu_percent(interval=0.2)
        ram_percent = psutil.virtual_memory().percent
        net = psutil.net_io_counters()
        return jsonify(
            {
                "cpu_usage": cpu_percent,
                "ram_usage": ram_percent,
                "bytes_sent": net.bytes_sent,
                "bytes_recv": net.bytes_recv,
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@storage.route("/api/backup_drive/drives", methods=["GET"])
@api_admin_required
def api_backup_drive_drives():
    services = _get_services()
    try:
        return jsonify(
            {
                "success": True,
                "drives": list_available_drives(runtime=services.runtime, ntfs_only=True),
            }
        )
    except Exception as exc:
        current_app.logger.error("Error listing backup drives: %s", exc)
        return jsonify({"success": False, "error": str(exc)})


@storage.route("/api/backup_drive/unmount", methods=["POST"])
@api_admin_required
def api_backup_drive_unmount():
    services = _get_services()
    try:
        data = request.get_json() or {}
        partition = data.get("partition")
        configured_mount_point = services.config_manager.get_value(
            "backup",
            "mount_point",
            services.runtime.default_mount_point,
        )
        configured_uuid = services.config_manager.get_value("backup", "uuid", "")

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
        return jsonify({"success": True, "message": message})
    except BackupDriveSetupError as exc:
        return jsonify({"success": False, "error": str(exc), "details": exc.details})
    except Exception as exc:
        current_app.logger.error("Error unmounting backup drive: %s", exc)
        return jsonify({"success": False, "error": "Could not unmount the selected drive."})


@storage.route("/api/backup_drive/configure", methods=["POST"])
@api_admin_required
def api_backup_drive_configure():
    services = _get_services()
    try:
        data = request.get_json() or {}
        result = apply_backup_drive_configuration(
            data.get("partition"),
            data.get("mount_point"),
            True,
            services.config_manager,
            services.smb_manager,
            runtime=services.runtime,
        )
        return jsonify({"success": True, "result": result})
    except BackupDriveSetupError as exc:
        return jsonify({"success": False, "error": str(exc), "details": exc.details})
    except Exception as exc:
        current_app.logger.error("Error configuring backup drive: %s", exc)
        return jsonify({"success": False, "error": "Could not configure the backup drive."})
