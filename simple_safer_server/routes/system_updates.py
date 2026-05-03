from typing import Any

from flask import Blueprint, current_app, render_template, session

from simple_safer_server.adapters.command_runner import CalledProcessError
from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_data, json_problem, json_request_data
from simple_safer_server.web.problems import ConflictProblem, OperationProblem, ValidationProblem

system_updates = Blueprint("system_updates_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


def _manager() -> Any:
    return _get_services().system_updates_manager


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
            }
        )
    except Exception:
        current_app.logger.exception("Error loading system update summary")
        return json_problem(OperationProblem("Failed to load system update summary."))


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
    except Exception:
        current_app.logger.exception("Could not start apt %s", operation)
        return json_problem(
            ConflictProblem(
                "Could not start the apt operation. Another package manager may be running.",
                slug="system-updates-operation-conflict",
            )
        )


@system_updates.route("/api/system_updates/stop", methods=["POST"])
@api_admin_required
def api_system_updates_stop():
    try:
        status = _manager().stop_operation()
        return json_data({"operation": status})
    except Exception:
        current_app.logger.exception("Could not stop apt operation")
        return json_problem(
            ConflictProblem(
                "Could not stop the apt operation. It may have already finished.",
                slug="system-updates-operation-conflict",
            )
        )


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
    except Exception:
        current_app.logger.exception("Could not remove stale apt locks")
        return json_problem(
            ConflictProblem(
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
