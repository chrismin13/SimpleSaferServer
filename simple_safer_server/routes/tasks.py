from typing import Any

import psutil
from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)

from simple_safer_server.core.backup_readiness import build_backup_readiness
from simple_safer_server.core.module_lifecycle import ModuleLifecycleError
from simple_safer_server.modules.storage.location import (
    get_storage_location,
    passive_storage_status,
)
from simple_safer_server.services.task_service import TASK_LOG_LINE_LIMIT, clamp_task_log_lines
from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_data, json_problem
from simple_safer_server.web.i18n import gettext
from simple_safer_server.web.problems import ConflictProblem, NotFoundProblem, OperationProblem

tasks = Blueprint("task_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


def _dashboard_ui_text() -> dict[str, Any]:
    """Return browser copy used by the dashboard script."""
    _ = gettext
    return {
        "status": {
            "checking": _("Checking…"),
            "dash": _("—"),
            "unknown": _("Unknown"),
            "success": _("Success"),
            "failure": _("Failure"),
            "running": _("Running"),
            "missing": _("Missing"),
            "notRunYet": _("Not Run Yet"),
            "stopped": _("Stopped"),
            "error": _("Error"),
            "unavailable": _("Unavailable"),
        },
        "actions": {
            "start": _("Start"),
            "stop": _("Stop"),
            "taskActionFailed": _("Task action failed."),
            "taskUpdated": _("Task updated."),
            "actionCompleted": _("Action completed successfully."),
            "actionFailed": _("Action failed."),
            "driveHealthRefreshed": _("Drive health refreshed."),
            "driveHealthRefreshFailed": _("Drive health refresh failed."),
        },
        "storage": {
            "settings": _("Storage Settings"),
            "mounted": _("Mounted"),
            "available": _("Available"),
            "notMounted": _("Not Mounted"),
            "unavailable": _("Unavailable"),
            "noStorageInfo": _("No storage info available"),
            "storageUnavailable": _("Storage is not available"),
            "usedTemplate": _("{used} / {total} GB used"),
            "mount": _("Mount Storage"),
            "mountConfirm": _("Are you sure you want to mount the storage drive?"),
            "mountConfirmTitle": _("Mount Storage"),
            "mountConfirmButton": _("Mount"),
            "unmount": _("Unmount Storage"),
            "unmountConfirmTitle": _("Unmount Storage"),
            "unmountConfirmButton": _("Unmount"),
            "unmountSoonTemplate": _(
                "This unmounts the configured backup drive temporarily.\n\n"
                "If it stays connected, SimpleSaferServer will remount it\n"
                "automatically during the next 'Check Mount' run (in about {countdown}).\n\n"
                "Remove the drive now if you do not want it mounted again."
            ),
            "unmountScheduled": _(
                "This unmounts the configured backup drive temporarily.\n\n"
                "If it stays connected, SimpleSaferServer will remount it\n"
                "automatically during the next scheduled 'Check Mount' run.\n\n"
                "Remove the drive now if you do not want it mounted again."
            ),
        },
        "health": {
            "noCheckYet": _("No check yet"),
            "notChecked": _("Not Checked"),
            "refreshToCheck": _("Refresh to check"),
            "healthy": _("Healthy"),
            "warning": _("Warning"),
            "critical": _("Critical"),
            "needsAttention": _("Needs Attention"),
            "checked": _("Checked"),
            "unknown": _("Unknown"),
            "noData": _("No Data"),
            "unavailable": _("Unavailable"),
            "dataUnavailable": _("Health data unavailable"),
            "healthTemplate": _("Health {value}%"),
            "tempTemplate": _("Temp {value}°C"),
        },
        "backup": {
            "ok": _("OK"),
            "failed": _("Failed"),
            "running": _("Running"),
            "never": _("Never"),
            "nextTemplate": _("Next: {time}"),
            "notScheduled": _("Not scheduled"),
            "unavailable": _("Unavailable"),
        },
        "sharing": {
            "operational": _("Operational"),
            "running": _("Running"),
            "servicesOperational": _("File sharing services operational"),
            "partial": _("Partial"),
            "degraded": _("Degraded"),
            "down": _("Down"),
            "notRunning": _("Not Running"),
            "unavailable": _("Unavailable"),
        },
    }


def _task_detail_ui_text() -> dict[str, Any]:
    """Return browser copy used by the task detail script."""
    _ = gettext
    return {
        "status": {
            "success": _("Success"),
            "failure": _("Failure"),
            "running": _("Running"),
            "missing": _("Missing"),
            "notRunYet": _("Not Run Yet"),
            "stopped": _("Stopped"),
            "unknown": _("Unknown"),
        },
        "refresh": {
            "reconnecting": _("Reconnecting to log..."),
            "retrying": _("Log refresh paused; retrying..."),
        },
        "schedule": {
            "unknown": _("Unknown"),
        },
    }


@tasks.route("/dashboard")
@admin_required
def dashboard():
    services = _get_services()
    if not services.config_manager.is_setup_complete():
        return redirect(url_for("setup.setup_page"))

    config = services.config_manager.get_all_config()
    task_summaries = services.task_service.task_summaries()
    storage_location = get_storage_location(services.config_manager, runtime=services.runtime)
    mount_point = storage_location.path
    mounted = (
        services.system_utils.is_mounted(mount_point)
        if storage_location.app_manages_mount
        else False
    )
    location_status = passive_storage_status(
        services.config_manager,
        services.system_utils,
        runtime=services.runtime,
    )
    disk = None
    storage_error = location_status["error"]
    try:
        # Disk usage only needs the path to be readable. The stricter marker
        # check still feeds the status text and cloud-backup safety gate.
        disk = psutil.disk_usage(mount_point)
    except OSError:
        current_app.logger.warning("Could not read storage usage for %s", mount_point)
    disk_available = disk is not None
    storage_available = bool(
        location_status["ok"] and (True if storage_location.app_manages_mount else disk_available)
    )
    if not storage_available and not storage_error and not storage_location.app_manages_mount:
        storage_error = "Storage path is not readable."

    cpu_percent = psutil.cpu_percent()
    ram_percent = psutil.virtual_memory().percent
    try:
        backup_readiness = build_backup_readiness(
            services.config_manager,
            runtime=services.runtime,
            smb_manager=getattr(services, "smb_manager", None),
        )
    except Exception:
        current_app.logger.exception("Failed to build backup readiness checklist")
        backup_readiness = None
    return render_template(
        "dashboard.html",
        used_storage=f"{disk.used / (1024**3):.1f}" if disk else "Unavailable",
        total_storage=f"{disk.total / (1024**3):.1f}" if disk else "Unavailable",
        storage_usage=f"{disk.percent}%" if disk else "Unavailable",
        cloud_backup_status=(
            "Active"
            if str(config.get("backup", {}).get("cloud_enabled", "false")).lower() == "true"
            else "Inactive"
        ),
        health_status="Not checked",
        hdd_temp="Not checked",
        cpu_usage=f"{cpu_percent}%",
        ram_usage=f"{ram_percent}%",
        mount_info={
            "is_mounted": mounted,
            "disk_available": disk_available,
            "mount_point": mount_point,
            "app_manages_mount": storage_location.app_manages_mount,
            "available": storage_available,
            "error": storage_error,
        },
        tasks=task_summaries,
        backup_readiness=backup_readiness,
        dashboard_ui_text=_dashboard_ui_text(),
    )


@tasks.route("/task/<task_name>")
@admin_required
def task_detail(task_name):
    task_service = _get_services().task_service
    task = task_service.get_task(task_name)
    if not task:
        abort(404)
    log_lines = TASK_LOG_LINE_LIMIT
    logs = task.get_logs(log_lines)
    return render_template(
        "task_detail.html",
        task=task,
        task_summary=task_service.task_summary(task),
        logs=logs,
        log_lines=log_lines,
        task_detail_ui_text=_task_detail_ui_text(),
    )


@tasks.route("/task/<task_name>/logs")
@admin_required
def task_logs(task_name):
    task = _get_services().task_service.get_task(task_name)
    if not task:
        abort(404)
    lines = clamp_task_log_lines(request.args.get("lines", TASK_LOG_LINE_LIMIT))
    logs = task.get_logs(lines)
    return logs, 200, {"Content-Type": "text/plain; charset=utf-8"}


@tasks.route("/api/tasks/<task_name>/status")
@api_admin_required
def api_task_status(task_name):
    task = _get_services().task_service.get_task(task_name)
    if not task:
        return json_problem(
            NotFoundProblem(
                gettext("Task not found."),
                title=gettext("Task not found"),
                slug="task-not-found",
            )
        )
    try:
        return json_data({"task": _get_services().task_service.task_summary(task)})
    except Exception:
        current_app.logger.exception("Failed to load task status for %s", task_name)
        return json_problem(OperationProblem(gettext("Failed to load task status.")))


@tasks.route("/task/<task_name>/start", methods=["POST"])
@admin_required
def start_task(task_name):
    task = _get_services().task_service.get_task(task_name)
    if not task:
        if request.accept_mimetypes.best == "application/json":
            return json_problem(
                NotFoundProblem(
                    gettext("Task not found."),
                    title=gettext("Task not found"),
                    slug="task-not-found",
                )
            )
        abort(404)
    try:
        task.start()
        if request.accept_mimetypes.best == "application/json":
            return json_data(
                {},
                message=gettext("Started {task_name}.").format(task_name=task_name),
            )
        return redirect(url_for("task_routes.task_detail", task_name=task_name))
    except ModuleLifecycleError as exc:
        if request.accept_mimetypes.best == "application/json":
            return json_problem(
                ConflictProblem(
                    str(exc),
                    title=gettext("Module setup required"),
                    slug="module-setup-required",
                )
            )
        abort(409)
    except Exception:
        current_app.logger.exception("Failed to start task %s", task_name)
        if request.accept_mimetypes.best == "application/json":
            return json_problem(
                OperationProblem(
                    gettext("Could not start task. Check task logs."),
                    slug="task-operation-failed",
                )
            )
        abort(500)


@tasks.route("/task/<task_name>/stop", methods=["POST"])
@admin_required
def stop_task(task_name):
    task = _get_services().task_service.get_task(task_name)
    if not task:
        if request.accept_mimetypes.best == "application/json":
            return json_problem(
                NotFoundProblem(
                    gettext("Task not found."),
                    title=gettext("Task not found"),
                    slug="task-not-found",
                )
            )
        abort(404)
    try:
        task.stop()
        if request.accept_mimetypes.best == "application/json":
            return json_data(
                {},
                message=gettext("Stopped {task_name}.").format(task_name=task_name),
            )
        return redirect(url_for("task_routes.task_detail", task_name=task_name))
    except Exception:
        current_app.logger.exception("Failed to stop task %s", task_name)
        if request.accept_mimetypes.best == "application/json":
            return json_problem(
                OperationProblem(
                    gettext("Could not stop task. Check task logs."),
                    slug="task-operation-failed",
                )
            )
        abort(500)


@tasks.route("/api/tasks/schedule")
@api_admin_required
def api_tasks_schedule():
    try:
        return json_data({"tasks": _get_services().task_service.task_summaries()})
    except Exception:
        current_app.logger.exception("Failed to load task schedule")
        return json_problem(OperationProblem(gettext("Failed to load task schedule.")))
