from typing import Any

from flask import Blueprint, current_app, render_template, request

from simple_safer_server.core.module_lifecycle import ModuleLifecycleError, require_module_applied
from simple_safer_server.core.privileged_client import PrivilegedActionClientError
from simple_safer_server.modules.drive_health.module import (
    create_module as create_drive_health_module,
)
from simple_safer_server.modules.drive_health.service import (
    SMART_FIELDS,
    build_drive_health_page_result,
    build_drive_health_summary,
    get_hdsentinel_settings,
    save_hdsentinel_settings,
)
from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_data, json_problem
from simple_safer_server.web.i18n import gettext
from simple_safer_server.web.problems import ConflictProblem, OperationProblem

drive_health = Blueprint("drive_health_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


def _require_drive_health_applied():
    services = _get_services()
    try:
        require_module_applied(create_drive_health_module(), services.runtime)
    except ModuleLifecycleError as exc:
        return json_problem(
            ConflictProblem(
                str(exc),
                title=gettext("Module setup required"),
                slug="module-setup-required",
            )
        )
    return None


@drive_health.route("/drives", methods=["GET", "POST"])
@admin_required
def drives():
    services = _get_services()
    error = None
    smart = None
    missing_attrs = []
    settings_message = None
    settings_error = None
    hdsentinel_settings = get_hdsentinel_settings(services.config_manager)
    # Page loads and settings saves must not probe disks or publish stale health.
    # HDSentinel data appears here only after an explicit health check POST.
    hdsentinel_snapshot = None
    hdsentinel_drives = []
    smart_support_warning = None

    if request.method == "POST":
        blocked = _require_drive_health_applied()
        if blocked:
            return blocked
        form_action = request.form.get("form_action", "run_health_check")
        if form_action == "save_hdsentinel_settings":
            try:
                save_hdsentinel_settings(
                    services.config_manager,
                    enabled=request.form.get("hdsentinel_enabled") == "on",
                    health_change_alert=request.form.get("hdsentinel_health_change_alert") == "on",
                )
                hdsentinel_settings = get_hdsentinel_settings(services.config_manager)
                settings_message = gettext("HDSentinel settings saved successfully.")
            except Exception as exc:
                settings_error = gettext("Failed to save HDSentinel settings: {error}").format(
                    error=exc
                )
        else:
            try:
                if services.runtime.is_fake:
                    result = build_drive_health_page_result(
                        services.config_manager,
                        services.system_utils,
                        runtime=services.runtime,
                    )
                else:
                    result = services.privileged_actions.run(
                        "drive-health.page-check",
                        {},
                    ).data
            except PrivilegedActionClientError as exc:
                error = str(exc)
                result = {
                    "summary": {
                        "status": "unknown",
                        "source": "live",
                        "checked_at": None,
                        "temperature": None,
                        "hdsentinel_health": None,
                        "hdsentinel_performance": None,
                        "detail": gettext(
                            "Drive health check failed. Check the application logs."
                        ),
                        "error": error,
                    }
                }

            smart = result.get("smart")
            missing_attrs = result.get("missing_attrs", [])
            error = result.get("error", error)
            hdsentinel_snapshot = result.get("hdsentinel_snapshot")
            hdsentinel_drives = result.get("hdsentinel_drives", [])
            smart_support_warning = result.get("smart_support_warning")
            if result.get("summary"):
                services.drive_health_summary_service.publish(result["summary"])

    return render_template(
        "drive_health.html",
        drive_health_module=create_drive_health_module(),
        smart=smart,
        error=error,
        missing_attrs=missing_attrs,
        smart_fields=SMART_FIELDS,
        hdsentinel_settings=hdsentinel_settings,
        hdsentinel_snapshot=hdsentinel_snapshot,
        hdsentinel_drives=hdsentinel_drives,
        smart_support_warning=smart_support_warning,
        settings_message=settings_message,
        settings_error=settings_error,
    )


@drive_health.route("/api/drive_health/summary")
@api_admin_required
def api_drive_health_summary():
    services = _get_services()
    try:
        return json_data(services.drive_health_summary_service.get_summary())
    except Exception as exc:
        current_app.logger.exception("Drive health summary lookup failed: %s", exc)
        return json_data(
            {
                "status": "unknown",
                "source": "memory",
                "checked_at": None,
                "temperature": None,
                "hdsentinel_health": None,
                "hdsentinel_performance": None,
                "detail": gettext("Drive health summary is unavailable."),
                "error": None,
            }
        )


@drive_health.route("/api/drive_health/refresh", methods=["POST"])
@api_admin_required
def api_drive_health_refresh():
    services = _get_services()
    try:
        blocked = _require_drive_health_applied()
        if blocked:
            return blocked
        if services.runtime.is_fake:
            summary = build_drive_health_summary(
                services.config_manager,
                services.system_utils,
                runtime=services.runtime,
            )
        else:
            summary = services.privileged_actions.run(
                "drive-health.refresh-summary",
                {},
            ).data.get("summary")
            if not isinstance(summary, dict):
                raise OperationProblem(gettext("Drive health refresh returned invalid data."))
        return json_data(services.drive_health_summary_service.publish(summary))
    except PrivilegedActionClientError as exc:
        current_app.logger.exception("Privileged drive health refresh failed: %s", exc)
        summary = {
            "status": "unknown",
            "source": "live",
            "checked_at": None,
            "temperature": None,
            "hdsentinel_health": None,
            "hdsentinel_performance": None,
            "detail": gettext("Drive health refresh failed. Check the application logs."),
            "error": str(exc),
        }
        services.drive_health_summary_service.publish(summary)
        return json_problem(OperationProblem(gettext("Drive health refresh failed.")))
    except Exception:
        current_app.logger.exception("Drive health refresh failed")
        summary = {
            "status": "unknown",
            "source": "live",
            "checked_at": None,
            "temperature": None,
            "hdsentinel_health": None,
            "hdsentinel_performance": None,
            "detail": gettext("Drive health refresh failed. Check the application logs."),
            "error": gettext("Drive health refresh failed."),
        }
        services.drive_health_summary_service.publish(summary)
        return json_problem(OperationProblem(gettext("Drive health refresh failed.")))
