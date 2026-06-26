from typing import Any

from flask import Blueprint, current_app, render_template, session

from simple_safer_server.core.module_lifecycle import ModuleLifecycleError, require_module_applied
from simple_safer_server.modules.ddns.module import create_module as create_ddns_module
from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_data, json_problem, json_request_data
from simple_safer_server.web.i18n import gettext
from simple_safer_server.web.problems import (
    ConflictProblem,
    NotFoundProblem,
    OperationProblem,
    ValidationProblem,
)

ddns = Blueprint("ddns_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


def _require_ddns_applied():
    services = _get_services()
    try:
        require_module_applied(create_ddns_module(), services.runtime)
    except ModuleLifecycleError as exc:
        return json_problem(
            ConflictProblem(
                str(exc),
                title=gettext("Module setup required"),
                slug="module-setup-required",
            )
        )
    return None


def _ddns_ui_text() -> dict[str, Any]:
    """Return browser copy used by the DDNS page script."""
    _ = gettext
    return {
        "status": {
            "never": _("Never"),
            "disabled": _("Disabled"),
            "pending": _("Pending"),
            "unknown": _("Unknown"),
            "success": _("Success"),
            "dash": _("—"),
        },
        "secrets": {
            "showToken": _("Show token"),
            "hideToken": _("Hide token"),
        },
        "messages": {
            "loadFailure": _("Connection error while loading DDNS configuration."),
            "saveSuccess": _("DDNS configuration saved."),
            "saveFailure": _("Connection error while saving."),
            "runSuccess": _("DDNS sync started successfully."),
            "runFailure": _("Failed to start DDNS sync."),
        },
        "confirmation": {
            "title": _("Run DDNS Checks"),
            "message": _("Are you sure you want to run DDNS checks manually now?"),
            "confirm": _("Run Now"),
            "running": _("Running..."),
        },
    }


@ddns.route("/ddns")
@admin_required
def ddns_page():
    module = create_ddns_module()
    return render_template(
        "ddns.html",
        username=session.get("username"),
        ddns_module=module,
        ddns_visible_warnings=module.help.warnings if _get_services().runtime.is_fake else (),
        ddns_ui_text=_ddns_ui_text(),
    )


@ddns.route("/api/ddns/config", methods=["GET"])
@api_admin_required
def get_ddns_config():
    try:
        return json_data(_get_services().ddns_service.get_config_payload())
    except Exception:
        current_app.logger.exception("Error loading DDNS configuration")
        return json_problem(OperationProblem(gettext("Failed to load DDNS configuration.")))


@ddns.route("/api/ddns/config", methods=["POST"])
@api_admin_required
def save_ddns_config():
    try:
        blocked = _require_ddns_applied()
        if blocked:
            return blocked
        data = json_request_data()
        message = _get_services().ddns_service.save_config(data)
        return json_data({}, message=message)
    except ValueError as exc:
        return json_problem(ValidationProblem(str(exc)))
    except Exception:
        current_app.logger.exception("Error saving DDNS configuration")
        return json_problem(OperationProblem(gettext("Failed to save DDNS configuration.")))


@ddns.route("/api/ddns/run", methods=["POST"])
@api_admin_required
def run_ddns_manual():
    try:
        blocked = _require_ddns_applied()
        if blocked:
            return blocked
        message = _get_services().ddns_service.run_manual()
        return json_data({}, message=message)
    except LookupError as exc:
        return json_problem(NotFoundProblem(str(exc), title=gettext("DDNS task not found")))
    except Exception:
        current_app.logger.exception("Error starting DDNS sync")
        return json_problem(OperationProblem(gettext("Failed to start DDNS sync.")))
