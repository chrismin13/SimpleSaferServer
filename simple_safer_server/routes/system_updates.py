from typing import Any

from flask import Blueprint, current_app, render_template, session

from simple_safer_server.adapters.command_runner import CalledProcessError
from simple_safer_server.services.app_updates import AppUpdateError
from simple_safer_server.services.system_updates import AptOperationConflict
from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_data, json_problem, json_request_data
from simple_safer_server.web.problems import ConflictProblem, OperationProblem, ValidationProblem

system_updates = Blueprint("system_updates_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


def _manager() -> Any:
    return _get_services().system_updates_manager


def _app_update_task_missing_problem():
    return json_problem(
        OperationProblem(
            "Application update task is not installed.",
            slug="application-update-task-missing",
        )
    )


def _start_app_update_task():
    task = _get_services().task_service.get_task("App Update")
    if task is None:
        return _app_update_task_missing_problem()
    task.start()
    return None


def _start_app_update_task_with_request(app_update_manager, queue_request):
    task = _get_services().task_service.get_task("App Update")
    if task is None:
        return _app_update_task_missing_problem()

    # app_update.service consumes this one-shot request at process startup, so
    # it must exist before systemd starts the task. Clear it if systemd refuses
    # the start so a later scheduled update cannot replay a stale admin intent.
    queue_request()
    try:
        task.start()
    except Exception:
        app_update_manager.clear_update_request()
        raise
    return None


@system_updates.route("/system_updates")
@admin_required
def system_updates_page():
    return render_template("system_updates.html", username=session.get("username"))


@system_updates.route("/api/system_updates/summary", methods=["GET"])
@api_admin_required
def api_system_updates_summary():
    try:
        manager = _manager()
        return json_data(
            {
                "distribution": manager.get_distribution_info(),
                "operation": manager.get_status(),
                "settings": manager.get_settings(),
                "livepatch": manager.get_livepatch_status(),
                "application": _get_services().app_update_manager.get_status(fetch_remote=False),
            }
        )
    except Exception:
        current_app.logger.exception("Error loading system update summary")
        return json_problem(OperationProblem("Failed to load system update summary."))


@system_updates.route("/api/system_updates/application/refresh", methods=["POST"])
@api_admin_required
def api_system_updates_application_refresh():
    try:
        return json_data(
            {"application": _get_services().app_update_manager.get_status(fetch_remote=True)}
        )
    except Exception:
        current_app.logger.exception("Error refreshing application update status")
        return json_problem(OperationProblem("Failed to refresh application update status."))


@system_updates.route("/api/system_updates/application/update", methods=["POST"])
@api_admin_required
def api_system_updates_application_update():
    try:
        app_update_manager = _get_services().app_update_manager
        status = app_update_manager.get_status(fetch_remote=False)
        if not status.get("can_update"):
            return json_problem(
                ConflictProblem(
                    status.get("message") or "Application update is not available.",
                    slug="application-update-not-available",
                )
            )
        problem_response = _start_app_update_task()
        if problem_response is not None:
            return problem_response
        return json_data(
            {
                "application": status,
                "task_url": "/task/App%20Update",
            },
            message="Application update started. Opening the App Update log.",
        )
    except AppUpdateError as exc:
        return json_problem(ConflictProblem(str(exc), slug="application-update-not-available"))
    except Exception:
        current_app.logger.exception("Could not start application update")
        return json_problem(OperationProblem("Could not start application update."))


@system_updates.route("/api/system_updates/application/force_update", methods=["POST"])
@api_admin_required
def api_system_updates_application_force_update():
    try:
        app_update_manager = _get_services().app_update_manager
        status = app_update_manager.get_status(fetch_remote=False)
        if not status.get("can_force_update"):
            return json_problem(
                ConflictProblem(
                    status.get("message") or "Application cleanup is not available.",
                    slug="application-force-update-not-available",
                )
            )
        problem_response = _start_app_update_task_with_request(
            app_update_manager,
            app_update_manager.request_cleanup_update,
        )
        if problem_response is not None:
            return problem_response
        return json_data(
            {
                "application": status,
                "task_url": "/task/App%20Update",
            },
            message="Application cleanup update started. Opening the App Update log.",
        )
    except AppUpdateError as exc:
        current_app.logger.warning("Application cleanup update failed: %s", exc)
        # Keep the UI wording action-oriented while preserving command output
        # for diagnostics in the Problem Details payload.
        return json_problem(
            OperationProblem(
                "Application cleanup update failed. Check logs before retrying.",
                slug="application-force-update-failed",
                extra={"diagnostic": str(exc)},
            )
        )
    except Exception:
        current_app.logger.exception("Could not clean up and update application")
        return json_problem(OperationProblem("Could not clean up and update application."))


@system_updates.route("/api/system_updates/application/branches", methods=["POST"])
@api_admin_required
def api_system_updates_application_branches():
    try:
        branches = _get_services().app_update_manager.list_remote_branches(fetch_remote=True)
        return json_data({"branches": branches})
    except AppUpdateError as exc:
        return json_problem(ConflictProblem(str(exc), slug="application-branches-unavailable"))
    except Exception:
        current_app.logger.exception("Could not load application branches")
        return json_problem(OperationProblem("Could not load application branches."))


@system_updates.route("/api/system_updates/application/switch_branch", methods=["POST"])
@api_admin_required
def api_system_updates_application_switch_branch():
    try:
        data = json_request_data()
        branch = data.get("branch") if isinstance(data, dict) else None
        if not isinstance(branch, str) or not branch.strip():
            return json_problem(ValidationProblem("Branch is required."))

        app_update_manager = _get_services().app_update_manager
        status = app_update_manager.get_status(fetch_remote=False)
        if status.get("dirty"):
            return json_problem(
                ConflictProblem(
                    "Clean up app folder before switching branches.",
                    slug="application-switch-branch-dirty",
                )
            )
        if branch not in app_update_manager.list_remote_branches(fetch_remote=True):
            return json_problem(
                ConflictProblem(
                    "Branch is no longer available. Refresh and try again.",
                    slug="application-switch-branch-unavailable",
                )
            )

        problem_response = _start_app_update_task_with_request(
            app_update_manager,
            lambda: app_update_manager.request_branch_switch(branch),
        )
        if problem_response is not None:
            return problem_response
        return json_data(
            {
                "task_url": "/task/App%20Update",
            },
            message="Application source switch started. Opening the App Update log.",
        )
    except AppUpdateError as exc:
        return json_problem(ConflictProblem(str(exc), slug="application-switch-branch-unavailable"))
    except Exception:
        current_app.logger.exception("Could not switch application branch")
        return json_problem(OperationProblem("Could not switch application branch."))


@system_updates.route("/api/system_updates/status", methods=["GET"])
@api_admin_required
def api_system_updates_status():
    try:
        return json_data({"operation": _manager().get_status()})
    except Exception:
        current_app.logger.exception("Error loading system update status")
        return json_problem(OperationProblem("Failed to load system update status."))


@system_updates.route("/api/system_updates/<operation>/start", methods=["POST"])
@api_admin_required
def api_system_updates_start(operation):
    try:
        status = _manager().start_operation(operation)
        return json_data({"operation": status})
    except ValueError as exc:
        return json_problem(ValidationProblem(str(exc)))
    except AptOperationConflict:
        current_app.logger.exception("Could not start apt %s", operation)
        return json_problem(
            ConflictProblem(
                "Could not start the apt operation. Another package manager may be running.",
                slug="system-updates-operation-conflict",
            )
        )
    except Exception:
        current_app.logger.exception("Could not start apt %s", operation)
        return json_problem(OperationProblem("Could not start the apt operation."))


@system_updates.route("/api/system_updates/stop", methods=["POST"])
@api_admin_required
def api_system_updates_stop():
    try:
        status = _manager().stop_operation()
        return json_data({"operation": status})
    except AptOperationConflict:
        current_app.logger.exception("Could not stop apt operation")
        return json_problem(
            ConflictProblem(
                "Could not stop the apt operation. It may have already finished.",
                slug="system-updates-operation-conflict",
            )
        )
    except Exception:
        current_app.logger.exception("Could not stop apt operation")
        return json_problem(OperationProblem("Could not stop the apt operation."))


@system_updates.route("/api/system_updates/settings", methods=["POST"])
@api_admin_required
def api_system_updates_save_settings():
    try:
        data = json_request_data()
        settings = _manager().save_settings(data)
        return json_data({"settings": settings})
    except Exception:
        current_app.logger.exception("Could not save apt update settings")
        return json_problem(OperationProblem("Could not save automatic update settings."))


@system_updates.route("/api/system_updates/remove_stale_locks", methods=["POST"])
@api_admin_required
def api_system_updates_remove_stale_locks():
    try:
        result = _manager().remove_stale_locks()
        message = result.get("message")
        return json_data({"removed": result.get("removed", [])}, message=message)
    except CalledProcessError:
        current_app.logger.exception("Could not remove stale apt locks")
        return json_problem(
            OperationProblem(
                "Could not remove stale apt locks. Check System Updates logs before retrying.",
                slug="system-updates-lock-removal-failed",
            )
        )
    except AptOperationConflict:
        current_app.logger.exception("Could not remove stale apt locks")
        return json_problem(
            ConflictProblem(
                "Could not remove stale apt locks. Check System Updates logs before retrying.",
                slug="system-updates-lock-removal-failed",
            )
        )
    except Exception:
        current_app.logger.exception("Could not remove stale apt locks")
        return json_problem(
            OperationProblem(
                "Could not remove stale apt locks. Check System Updates logs before retrying.",
                slug="system-updates-lock-removal-failed",
            )
        )


@system_updates.route("/api/system_updates/livepatch/setup", methods=["POST"])
@api_admin_required
def api_system_updates_livepatch_setup():
    try:
        data = json_request_data()
        status = _manager().setup_livepatch(data.get("token", ""))
        return json_data({"livepatch": status})
    except ValidationProblem as exc:
        return json_problem(exc)
    except ValueError as exc:
        # Livepatch setup has operator-facing validation before it reaches
        # privileged commands; keep those failures as 400 Problem Details.
        return json_problem(ValidationProblem(str(exc)))
    except CalledProcessError:
        current_app.logger.exception("Could not set up Livepatch")
        return json_problem(
            OperationProblem(
                "Could not set up Livepatch. Check the token and retry.",
                slug="livepatch-setup-failed",
            )
        )
    except Exception:
        current_app.logger.exception("Could not set up Livepatch")
        return json_problem(
            OperationProblem(
                "Could not set up Livepatch. Check the token and retry.",
                slug="livepatch-setup-failed",
            )
        )
