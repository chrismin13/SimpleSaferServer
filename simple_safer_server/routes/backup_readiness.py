from flask import Blueprint, current_app, render_template

from simple_safer_server.core.backup_readiness import build_backup_readiness
from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_data, json_problem
from simple_safer_server.web.i18n import gettext
from simple_safer_server.web.problems import OperationProblem

backup_readiness = Blueprint("backup_readiness", __name__)


def _build_dashboard_readiness():
    """Build the shared dashboard/setup backup checklist from app services."""
    services = current_app.extensions["simple_safer_server"]
    return build_backup_readiness(
        services.config_manager,
        runtime=services.runtime,
        smb_manager=services.smb_manager,
    )


@backup_readiness.route("/api/backup-readiness", methods=["GET"])
@api_admin_required
def get_backup_readiness():
    """Return the shared backup-protection checklist for dashboard UI."""
    try:
        return json_data(_build_dashboard_readiness())
    except Exception:
        current_app.logger.exception("Failed to build backup readiness checklist")
        return json_problem(OperationProblem(gettext("Failed to load backup readiness.")))


@backup_readiness.route("/fragments/backup-readiness", methods=["GET"])
@admin_required
def backup_readiness_fragment():
    """Return the dashboard checklist as an HTML fragment for htmx refreshes."""
    try:
        return render_template(
            "partials/backup_readiness_fragment.html",
            readiness=_build_dashboard_readiness(),
            title=gettext("Backup protection"),
            refresh_url="/fragments/backup-readiness",
        )
    except Exception:
        current_app.logger.exception("Failed to render backup readiness checklist")
        return render_template(
            "partials/backup_readiness_fragment.html",
            readiness=None,
            title=gettext("Backup protection"),
            refresh_url="/fragments/backup-readiness",
        ), 500
