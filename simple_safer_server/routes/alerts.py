from typing import Any

from flask import Blueprint, current_app, render_template, session

from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_data, json_problem, json_request_data
from simple_safer_server.web.problems import ApiProblem, OperationProblem

alerts = Blueprint("alerts_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


@alerts.route("/alerts")
@admin_required
def alerts_page():
    return render_template("alerts.html", username=session.get("username"))


@alerts.route("/api/alerts/generate-test", methods=["POST"])
@api_admin_required
def api_generate_test_alerts():
    try:
        _get_services().alerts_service.generate_test_alerts()
        return json_data({}, message="Test alerts generated.")
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Error generating test alerts")
        return json_problem(OperationProblem("Failed to generate test alerts."))


@alerts.route("/api/alerts", methods=["GET"])
@api_admin_required
def api_get_alerts():
    try:
        return json_data(_get_services().alerts_service.get_alerts())
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Error getting alerts")
        return json_problem(OperationProblem("Failed to get alerts."))


@alerts.route("/api/alerts/<int:alert_id>", methods=["GET"])
@api_admin_required
def api_get_alert(alert_id):
    try:
        return json_data(_get_services().alerts_service.get_alert(alert_id))
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Error getting alert %s", alert_id)
        return json_problem(OperationProblem("Failed to get alert."))


@alerts.route("/api/alerts/<int:alert_id>/mark-read", methods=["POST"])
@api_admin_required
def api_mark_alert_read(alert_id):
    try:
        _get_services().alerts_service.mark_alert_read(alert_id)
        return json_data({}, message="Alert marked as read.")
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Error marking alert %s as read", alert_id)
        return json_problem(OperationProblem("Failed to mark alert read."))


@alerts.route("/api/alerts/clear", methods=["POST"])
@api_admin_required
def api_clear_alerts():
    try:
        _get_services().alerts_service.clear_alerts()
        return json_data({}, message="Alerts cleared.")
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Error clearing alerts")
        return json_problem(OperationProblem("Failed to clear alerts."))


@alerts.route("/api/alerts/mark-all-read", methods=["POST"])
@api_admin_required
def api_mark_all_alerts_read():
    try:
        _get_services().alerts_service.mark_all_alerts_read()
        return json_data({}, message="Alerts marked as read.")
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Error marking all alerts as read")
        return json_problem(OperationProblem("Failed to mark alerts read."))


@alerts.route("/api/alerts/email-config", methods=["GET"])
@api_admin_required
def api_get_email_config():
    try:
        return json_data(_get_services().alerts_service.get_email_config())
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Error getting email config")
        return json_problem(OperationProblem("Failed to get email config."))


@alerts.route("/api/alerts/email-config", methods=["POST"])
@api_admin_required
def api_set_email_config():
    try:
        data = json_request_data("JSON object is required.")
        _get_services().alerts_service.save_email_config(data)
        return json_data({}, message="Email settings saved.")
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception:
        current_app.logger.exception("Error setting email config")
        return json_problem(OperationProblem("Failed to set email config."))
