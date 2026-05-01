from typing import Any

from flask import Blueprint, current_app, jsonify, render_template, request, session

from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import service_json_response

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
        payload, status_code = _get_services().alerts_service.generate_test_alerts()
        return jsonify(payload) if status_code == 200 else (jsonify(payload), status_code)
    except Exception:
        current_app.logger.exception("Error generating test alerts")
        return jsonify({"success": False, "error": "Failed to generate test alerts"}), 500


@alerts.route("/api/alerts", methods=["GET"])
@api_admin_required
def api_get_alerts():
    try:
        payload = _get_services().alerts_service.get_alerts()
        if not payload.get("success"):
            current_app.logger.error("Alerts service returned failure while listing alerts")
        return service_json_response(payload)
    except Exception:
        current_app.logger.exception("Error getting alerts")
        return jsonify({"success": False, "error": "Failed to get alerts"}), 500


@alerts.route("/api/alerts/<int:alert_id>", methods=["GET"])
@api_admin_required
def api_get_alert(alert_id):
    try:
        payload, status_code = _get_services().alerts_service.get_alert(alert_id)
        if status_code == 200:
            return jsonify(payload)
        return jsonify(payload), status_code
    except Exception:
        current_app.logger.exception("Error getting alert %s", alert_id)
        return jsonify({"success": False, "error": "Failed to get alert"}), 500


@alerts.route("/api/alerts/<int:alert_id>/mark-read", methods=["POST"])
@api_admin_required
def api_mark_alert_read(alert_id):
    try:
        payload = _get_services().alerts_service.mark_alert_read(alert_id)
        return service_json_response(payload)
    except Exception:
        current_app.logger.exception("Error marking alert %s as read", alert_id)
        return jsonify({"success": False, "error": "Failed to mark alert read"}), 500


@alerts.route("/api/alerts/clear", methods=["POST"])
@api_admin_required
def api_clear_alerts():
    try:
        payload = _get_services().alerts_service.clear_alerts()
        return service_json_response(payload)
    except Exception:
        current_app.logger.exception("Error clearing alerts")
        return jsonify({"success": False, "error": "Failed to clear alerts"}), 500


@alerts.route("/api/alerts/mark-all-read", methods=["POST"])
@api_admin_required
def api_mark_all_alerts_read():
    try:
        payload = _get_services().alerts_service.mark_all_alerts_read()
        return service_json_response(payload)
    except Exception:
        current_app.logger.exception("Error marking all alerts as read")
        return jsonify({"success": False, "error": "Failed to mark alerts read"}), 500


@alerts.route("/api/alerts/email-config", methods=["GET"])
@api_admin_required
def api_get_email_config():
    try:
        return jsonify(_get_services().alerts_service.get_email_config())
    except Exception:
        current_app.logger.exception("Error getting email config")
        return jsonify({"success": False, "error": "Failed to get email config"}), 500


@alerts.route("/api/alerts/email-config", methods=["POST"])
@api_admin_required
def api_set_email_config():
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"success": False, "error": "JSON object is required"}), 400
        payload = _get_services().alerts_service.save_email_config(data)
        return service_json_response(payload, failure_status=400)
    except Exception:
        current_app.logger.exception("Error setting email config")
        return jsonify({"success": False, "error": "Failed to set email config"}), 500
