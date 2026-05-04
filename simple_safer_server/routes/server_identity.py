from typing import Any

from flask import Blueprint, current_app

from simple_safer_server.services.server_identity import ServerIdentityError
from simple_safer_server.services.user_manager import api_admin_required
from simple_safer_server.web.api import json_data, json_problem, json_request_data
from simple_safer_server.web.problems import OperationProblem, ValidationProblem

server_identity = Blueprint("server_identity_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


@server_identity.route("/api/server_identity", methods=["GET"])
@api_admin_required
def api_get_server_identity():
    try:
        return json_data(_get_services().server_identity_service.current_identity())
    except Exception:
        current_app.logger.exception("Failed to read server identity")
        return json_problem(OperationProblem("Failed to read server name."))


@server_identity.route("/api/server_identity", methods=["PUT"])
@api_admin_required
def api_update_server_identity():
    try:
        data = json_request_data()
        result = _get_services().server_identity_service.update_server_name(
            data.get("server_name"),
            restart_samba=True,
        )
        message = "Server name updated."
        if result.warning:
            message = f"{message} {result.warning}"
        return json_data(result, message=message)
    except ServerIdentityError as exc:
        return json_problem(ValidationProblem(str(exc), slug="server-identity-validation-error"))
    except Exception:
        current_app.logger.exception("Failed to update server identity")
        return json_problem(
            OperationProblem(
                "Failed to update server name.",
                slug="server-identity-operation-failed",
            )
        )
