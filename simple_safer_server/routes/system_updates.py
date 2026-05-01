from typing import Any

from flask import Blueprint, current_app, render_template, session

from simple_safer_server.adapters.command_runner import CalledProcessError
from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_error, json_payload_or_error, json_success

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
        return json_success(
            distribution=manager.get_distribution_info(),
            operation=manager.get_status(),
            settings=manager.get_settings(),
            livepatch=manager.get_livepatch_status(),
        )
    except Exception:
        current_app.logger.exception("Error loading system update summary")
        return json_error("Failed to load system update summary.", status_code=500)


@system_updates.route("/api/system_updates/status", methods=["GET"])
@api_admin_required
def api_system_updates_status():
    try:
        return json_success(operation=_manager().get_status())
    except Exception:
        current_app.logger.exception("Error loading system update status")
        return json_error("Failed to load system update status.", status_code=500)


@system_updates.route("/api/system_updates/<operation>/start", methods=["POST"])
@api_admin_required
def api_system_updates_start(operation):
    try:
        status = _manager().start_operation(operation)
        return json_success(operation=status)
    except ValueError as exc:
        return json_error(str(exc), status_code=400)
    except Exception:
        current_app.logger.exception("Could not start apt %s", operation)
        return json_error(
            "Could not start the apt operation. Another package manager may be running.",
            status_code=409,
        )


@system_updates.route("/api/system_updates/stop", methods=["POST"])
@api_admin_required
def api_system_updates_stop():
    try:
        status = _manager().stop_operation()
        return json_success(operation=status)
    except Exception:
        current_app.logger.exception("Could not stop apt operation")
        return json_error(
            "Could not stop the apt operation. It may have already finished.",
            status_code=409,
        )


@system_updates.route("/api/system_updates/settings", methods=["POST"])
@api_admin_required
def api_system_updates_save_settings():
    try:
        data, error_response = json_payload_or_error()
        if error_response:
            return error_response
        settings = _manager().save_settings(data)
        return json_success(settings=settings)
    except Exception:
        current_app.logger.exception("Could not save apt update settings")
        return json_error(
            "Could not save automatic update settings.",
            status_code=500,
        )


@system_updates.route("/api/system_updates/remove_stale_locks", methods=["POST"])
@api_admin_required
def api_system_updates_remove_stale_locks():
    try:
        result = _manager().remove_stale_locks()
        return json_success(**result)
    except CalledProcessError:
        current_app.logger.exception("Could not remove stale apt locks")
        return json_error(
            "Could not remove stale apt locks. Check System Updates logs before retrying.",
            status_code=500,
        )
    except Exception:
        current_app.logger.exception("Could not remove stale apt locks")
        return json_error(
            "Could not remove stale apt locks. Check System Updates logs before retrying.",
            status_code=409,
        )


@system_updates.route("/api/system_updates/livepatch/setup", methods=["POST"])
@api_admin_required
def api_system_updates_livepatch_setup():
    try:
        data, error_response = json_payload_or_error()
        if error_response:
            return error_response
        status = _manager().setup_livepatch(data.get("token", ""))
        return json_success(livepatch=status)
    except CalledProcessError:
        current_app.logger.exception("Could not set up Livepatch")
        return json_error("Could not set up Livepatch. Check the token and retry.", status_code=500)
    except Exception:
        current_app.logger.exception("Could not set up Livepatch")
        return json_error("Could not set up Livepatch. Check the token and retry.", status_code=500)
