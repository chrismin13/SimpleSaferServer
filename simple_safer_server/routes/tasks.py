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

from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_data, json_problem
from simple_safer_server.web.problems import NotFoundProblem, OperationProblem

tasks = Blueprint("task_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


@tasks.route("/dashboard")
@admin_required
def dashboard():
    services = _get_services()
    if not services.config_manager.is_setup_complete():
        return redirect(url_for("setup.setup_page"))

    config = services.config_manager.get_all_config()
    task_summaries = services.task_service.task_summaries()
    mount_point = services.config_manager.get_value(
        "backup",
        "mount_point",
        services.runtime.default_mount_point,
    )
    mounted = services.system_utils.is_mounted(mount_point)
    disk = None
    if mounted:
        try:
            disk = psutil.disk_usage(mount_point)
        except Exception:
            current_app.logger.exception("Could not read backup drive usage for %s", mount_point)

    cpu_percent = psutil.cpu_percent()
    ram_percent = psutil.virtual_memory().percent
    return render_template(
        "dashboard.html",
        used_storage=f"{disk.used / (1024**3):.1f}" if disk else "Unavailable",
        total_storage=f"{disk.total / (1024**3):.1f}" if disk else "Unavailable",
        storage_usage=f"{disk.percent}%" if disk else "Unavailable",
        cloud_backup_status="Active" if config.get("backup", {}).get("rclone_dir") else "Inactive",
        health_status="Not checked",
        hdd_temp="Not checked",
        cpu_usage=f"{cpu_percent}%",
        ram_usage=f"{ram_percent}%",
        mount_info={
            "is_mounted": mounted,
            "disk_available": disk is not None,
            "mount_point": mount_point,
        },
        tasks=task_summaries,
    )


@tasks.route("/task/<task_name>")
@admin_required
def task_detail(task_name):
    task = _get_services().task_service.get_task(task_name)
    if not task:
        abort(404)
    logs = task.get_logs()
    return render_template("task_detail.html", task=task, logs=logs)


@tasks.route("/task/<task_name>/logs")
@admin_required
def task_logs(task_name):
    task = _get_services().task_service.get_task(task_name)
    if not task:
        abort(404)
    try:
        lines = int(request.args.get("lines", 50))
    except (TypeError, ValueError):
        lines = 50
    lines = max(1, min(lines, 500))
    logs = task.get_logs(lines)
    return logs, 200, {"Content-Type": "text/plain; charset=utf-8"}


@tasks.route("/task/<task_name>/start", methods=["POST"])
@admin_required
def start_task(task_name):
    task = _get_services().task_service.get_task(task_name)
    if not task:
        if request.accept_mimetypes.best == "application/json":
            return json_problem(
                NotFoundProblem("Task not found.", title="Task not found", slug="task-not-found")
            )
        abort(404)
    try:
        task.start()
        if request.accept_mimetypes.best == "application/json":
            return json_data({}, message=f"Started {task_name}.")
        return redirect(url_for("task_routes.task_detail", task_name=task_name))
    except Exception:
        current_app.logger.exception("Failed to start task %s", task_name)
        if request.accept_mimetypes.best == "application/json":
            return json_problem(
                OperationProblem(
                    "Could not start task. Check task logs.", slug="task-operation-failed"
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
                NotFoundProblem("Task not found.", title="Task not found", slug="task-not-found")
            )
        abort(404)
    try:
        task.stop()
        if request.accept_mimetypes.best == "application/json":
            return json_data({}, message=f"Stopped {task_name}.")
        return redirect(url_for("task_routes.task_detail", task_name=task_name))
    except Exception:
        current_app.logger.exception("Failed to stop task %s", task_name)
        if request.accept_mimetypes.best == "application/json":
            return json_problem(
                OperationProblem(
                    "Could not stop task. Check task logs.", slug="task-operation-failed"
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
        return json_problem(OperationProblem("Failed to load task schedule."))
