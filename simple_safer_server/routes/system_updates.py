from typing import Any

from flask import Blueprint, current_app, render_template, request, session

from simple_safer_server.adapters.command_runner import CalledProcessError
from simple_safer_server.web.api import json_error, json_success
from simple_safer_server.services.user_manager import admin_required, api_admin_required

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
    except Exception as exc:
        current_app.logger.exception("Error loading system update summary")
        return json_error(str(exc), status_code=500)


@system_updates.route("/api/system_updates/status", methods=["GET"])
@api_admin_required
def api_system_updates_status():
    try:
        return json_success(operation=_manager().get_status())
    except Exception as exc:
        current_app.logger.exception("Error loading system update status")
        return json_error(str(exc), status_code=500)


@system_updates.route("/api/system_updates/<operation>/start", methods=["POST"])
@api_admin_required
def api_system_updates_start(operation):
    try:
        status = _manager().start_operation(operation)
        return json_success(operation=status)
    except ValueError as exc:
        return json_error(str(exc), status_code=400)
    except Exception as exc:
        current_app.logger.warning("Could not start apt %s: %s", operation, exc)
        return json_error(str(exc), status_code=409)


@system_updates.route("/api/system_updates/stop", methods=["POST"])
@api_admin_required
def api_system_updates_stop():
    try:
        status = _manager().stop_operation()
        return json_success(operation=status)
    except Exception as exc:
        current_app.logger.warning("Could not stop apt operation: %s", exc)
        return json_error(str(exc), status_code=409)


@system_updates.route("/api/system_updates/settings", methods=["POST"])
@api_admin_required
def api_system_updates_save_settings():
    try:
        settings = _manager().save_settings(request.get_json() or {})
        return json_success(settings=settings)
    except CalledProcessError as exc:
        message = exc.stderr.strip() if exc.stderr else str(exc)
        return json_error(message, status_code=500)
    except Exception as exc:
        current_app.logger.exception("Could not save apt update settings")
        return json_error(str(exc), status_code=500)


@system_updates.route("/api/system_updates/remove_stale_locks", methods=["POST"])
@api_admin_required
def api_system_updates_remove_stale_locks():
    try:
        result = _manager().remove_stale_locks()
        return json_success(**result)
    except CalledProcessError as exc:
        message = exc.stderr.strip() if exc.stderr else str(exc)
        return json_error(message, status_code=500)
    except Exception as exc:
        current_app.logger.warning("Could not remove stale apt locks: %s", exc)
        return json_error(str(exc), status_code=409)


@system_updates.route("/api/system_updates/livepatch/setup", methods=["POST"])
@api_admin_required
def api_system_updates_livepatch_setup():
    try:
        data = request.get_json() or {}
        status = _manager().setup_livepatch(data.get("token", ""))
        return json_success(livepatch=status)
    except CalledProcessError as exc:
        message = exc.stderr.strip() if exc.stderr else str(exc)
        return json_error(message, status_code=500)
    except Exception as exc:
        current_app.logger.warning("Could not set up Livepatch: %s", exc)
        return json_error(str(exc), status_code=400)
