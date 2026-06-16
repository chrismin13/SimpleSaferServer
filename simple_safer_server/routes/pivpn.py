from typing import Any

from flask import Blueprint, current_app, render_template, session

from simple_safer_server.services.user_manager import admin_required

pivpn = Blueprint("pivpn_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


@pivpn.route("/pivpn")
@admin_required
def pivpn_page():
    return render_template(
        "pivpn.html",
        username=session.get("username"),
        pivpn_status=_get_services().pivpn_service.get_page_status(),
    )
