from typing import Any

from flask import Blueprint, current_app, render_template, session

from simple_safer_server.services.user_manager import admin_required

tailscale = Blueprint("tailscale_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


@tailscale.route("/tailscale")
@admin_required
def tailscale_page():
    summary = _get_services().tailscale_service.get_summary()
    return render_template(
        "tailscale.html",
        username=session.get("username"),
        summary=summary,
    )
