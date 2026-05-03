from typing import Any

from flask import Blueprint, current_app, render_template, session

from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_data, json_problem, json_request_data
from simple_safer_server.web.problems import NotFoundProblem, OperationProblem, ValidationProblem

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
        return json_data(_get_services().ddns_service.get_config_payload())
    except Exception:
        current_app.logger.exception("Error loading DDNS configuration")
        return json_problem(OperationProblem("Failed to load DDNS configuration."))


@ddns.route("/api/ddns/config", methods=["POST"])
@api_admin_required
def save_ddns_config():
    try:
        data = json_request_data()
        message = _get_services().ddns_service.save_config(data)
        return json_data({}, message=message)
    except ValueError as exc:
        return json_problem(ValidationProblem(str(exc)))
    except Exception:
        current_app.logger.exception("Error saving DDNS configuration")
        return json_problem(OperationProblem("Failed to save DDNS configuration."))


@ddns.route("/api/ddns/run", methods=["POST"])
@api_admin_required
def run_ddns_manual():
    try:
        message = _get_services().ddns_service.run_manual()
        return json_data({}, message=message)
    except LookupError as exc:
        return json_problem(NotFoundProblem(str(exc), title="DDNS task not found"))
    except Exception:
        current_app.logger.exception("Error starting DDNS sync")
        return json_problem(OperationProblem("Failed to start DDNS sync."))
