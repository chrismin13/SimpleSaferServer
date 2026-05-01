from typing import Any

from flask import Blueprint, current_app, jsonify, render_template, session

from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_error, json_payload_or_error, json_success

ddns = Blueprint("ddns_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


@ddns.route("/ddns")
@admin_required
def ddns_page():
    return render_template("ddns.html", username=session.get("username"))


@ddns.route("/api/ddns/config", methods=["GET"])
@api_admin_required
def get_ddns_config():
    try:
        return jsonify(_get_services().ddns_service.get_config_payload())
    except Exception:
        current_app.logger.exception("Error loading DDNS configuration")
        return json_error("Failed to load DDNS configuration.", status_code=500, key="message")


@ddns.route("/api/ddns/config", methods=["POST"])
@api_admin_required
def save_ddns_config():
    try:
        data, error_response = json_payload_or_error()
        if error_response:
            return error_response
        message = _get_services().ddns_service.save_config(data)
        return json_success(message=message)
    except ValueError as exc:
        return json_error(str(exc), status_code=400, key="message")
    except Exception:
        current_app.logger.exception("Error saving DDNS configuration")
        return json_error("Failed to save DDNS configuration.", status_code=500, key="message")


@ddns.route("/api/ddns/run", methods=["POST"])
@api_admin_required
def run_ddns_manual():
    try:
        message = _get_services().ddns_service.run_manual()
        return json_success(message=message)
    except LookupError as exc:
        return json_error(str(exc), status_code=404, key="message")
    except Exception:
        current_app.logger.exception("Error starting DDNS sync")
        return json_error("Failed to start DDNS sync.", status_code=500, key="message")
