from typing import Any

from flask import Blueprint, current_app, render_template, session

from simple_safer_server.core.module_lifecycle import ModuleLifecycleError, require_module_applied
from simple_safer_server.modules.alerts.module import create_module as create_alerts_module
from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_data, json_problem, json_request_data
from simple_safer_server.web.i18n import gettext
from simple_safer_server.web.problems import ApiProblem, ConflictProblem, OperationProblem

alerts = Blueprint("alerts_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


def _require_alerts_setup() -> None:
    services = _get_services()
    require_module_applied(create_alerts_module(), services.runtime)


def _alerts_ui_text() -> dict[str, Any]:
    """Return browser copy used by the Alerts page script."""
    _ = gettext
    return {
        "settings": {
            "open": _("Email Settings"),
            "close": _("Close Settings"),
            "saved": _("Email configuration saved successfully."),
            "required": _("Email, from address, SMTP server, port, and username are required."),
            "invalidEmail": _("Please enter a valid email address."),
            "invalidFrom": _("Please enter a valid from address."),
            "portDigits": _("SMTP port must contain only digits."),
            "portRange": _("SMTP port must be between 1 and 65535."),
            "saveFailure": _("An error occurred while saving."),
            "showPassword": _("Show password"),
            "hidePassword": _("Hide password"),
        },
        "alerts": {
            "generateFailure": _("Network error while generating test alerts."),
            "loadFailure": _("Could not load alerts due to a network error."),
            "detailFailure": _("Failed to load alert."),
            "markReadFailure": _("Failed to mark alert read."),
            "clearFailure": _("Network error while clearing alerts."),
            "markAllFailure": _("Network error while marking alerts as read."),
            "openDetails": _("Open {title} alert details"),
        },
        "badges": {
            "error": _("Error"),
            "warning": _("Warning"),
            "info": _("Info"),
            "success": _("Success"),
            "read": _("Read"),
            "new": _("New"),
        },
    }


@alerts.route("/alerts")
@admin_required
def alerts_page():
    return render_template(
        "alerts.html",
        username=session.get("username"),
        alerts_module=create_alerts_module(),
        alerts_ui_text=_alerts_ui_text(),
    )


@alerts.route("/api/alerts/generate-test", methods=["POST"])
@api_admin_required
def api_generate_test_alerts():
    try:
        _get_services().alerts_service.generate_test_alerts()
        return json_data({}, message=gettext("Test alerts generated."))
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Error generating test alerts")
        return json_problem(OperationProblem(gettext("Failed to generate test alerts.")))


@alerts.route("/api/alerts", methods=["GET"])
@api_admin_required
def api_get_alerts():
    try:
        return json_data(_get_services().alerts_service.get_alerts())
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Error getting alerts")
        return json_problem(OperationProblem(gettext("Failed to get alerts.")))


@alerts.route("/api/alerts/<int:alert_id>", methods=["GET"])
@api_admin_required
def api_get_alert(alert_id):
    try:
        return json_data(_get_services().alerts_service.get_alert(alert_id))
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Error getting alert %s", alert_id)
        return json_problem(OperationProblem(gettext("Failed to get alert.")))


@alerts.route("/api/alerts/<int:alert_id>/mark-read", methods=["POST"])
@api_admin_required
def api_mark_alert_read(alert_id):
    try:
        _get_services().alerts_service.mark_alert_read(alert_id)
        return json_data({}, message=gettext("Alert marked as read."))
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Error marking alert %s as read", alert_id)
        return json_problem(OperationProblem(gettext("Failed to mark alert read.")))


@alerts.route("/api/alerts/clear", methods=["POST"])
@api_admin_required
def api_clear_alerts():
    try:
        _get_services().alerts_service.clear_alerts()
        return json_data({}, message=gettext("Alerts cleared."))
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Error clearing alerts")
        return json_problem(OperationProblem(gettext("Failed to clear alerts.")))


@alerts.route("/api/alerts/mark-all-read", methods=["POST"])
@api_admin_required
def api_mark_all_alerts_read():
    try:
        _get_services().alerts_service.mark_all_alerts_read()
        return json_data({}, message=gettext("Alerts marked as read."))
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Error marking all alerts as read")
        return json_problem(OperationProblem(gettext("Failed to mark alerts read.")))


@alerts.route("/api/alerts/email-config", methods=["GET"])
@api_admin_required
def api_get_email_config():
    try:
        return json_data(_get_services().alerts_service.get_email_config())
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Error getting email config")
        return json_problem(OperationProblem(gettext("Failed to get email config.")))


@alerts.route("/api/alerts/email-config", methods=["POST"])
@api_admin_required
def api_set_email_config():
    try:
        _require_alerts_setup()
        data = json_request_data(gettext("JSON object is required."))
        _get_services().alerts_service.save_email_config(data)
        return json_data({}, message=gettext("Email settings saved."))
    except ModuleLifecycleError as exc:
        return json_problem(
            ConflictProblem(
                str(exc),
                title=gettext("Module setup required"),
                slug="module-setup-required",
            )
        )
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Error setting email config")
        return json_problem(OperationProblem(gettext("Failed to set email config.")))
