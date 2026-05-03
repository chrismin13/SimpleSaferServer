import subprocess
from datetime import datetime
from typing import Any

from flask import Blueprint, abort, current_app, render_template, request, send_file

from simple_safer_server.services.drive_health import (
    SMART_FIELDS,
    SMARTCTL_JSON_UPGRADE_MESSAGE,
    append_telemetry,
    build_drive_health_summary,
    collect_hdsentinel_snapshot,
    get_hdsentinel_display_snapshot,
    get_hdsentinel_settings,
    get_optimal_threshold,
    get_smart_attributes,
    get_smartctl_json_support,
    predict_failure_probability,
    save_hdsentinel_settings,
)
from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_data, json_problem
from simple_safer_server.web.problems import NotFoundProblem, OperationProblem

drive_health = Blueprint("drive_health_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    from flask import current_app

    return current_app.extensions["simple_safer_server"]


@drive_health.route("/drives", methods=["GET", "POST"])
@admin_required
def drives():
    services = _get_services()
    prediction = None
    probability = None
    error = None
    smart = None
    missing_attrs = []
    settings_message = None
    settings_error = None
    hdsentinel_settings = get_hdsentinel_settings(services.config_manager)
    hdsentinel_snapshot = get_hdsentinel_display_snapshot(
        services.config_manager,
        services.system_utils,
        runtime=services.runtime,
    )
    drive_config = {
        "mount_point": services.config_manager.get_value(
            "backup", "mount_point", services.runtime.default_mount_point
        ),
        "uuid": services.config_manager.get_value("backup", "uuid", ""),
        "usb_id": services.config_manager.get_value("backup", "usb_id", ""),
    }

    smart_support_warning = None
    if not services.runtime.is_fake:
        try:
            smartctl_json_supported, smartctl_json_error = get_smartctl_json_support()
            if not smartctl_json_supported:
                smart_support_warning = smartctl_json_error
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
            smart_support_warning = f"Could not check smartctl JSON support: {exc}"
        except Exception as exc:
            smart_support_warning = f"Could not check smartctl JSON support: {exc}"

    if request.method == "POST":
        form_action = request.form.get("form_action", "run_health_check")
        if form_action == "save_hdsentinel_settings":
            try:
                save_hdsentinel_settings(
                    services.config_manager,
                    enabled=request.form.get("hdsentinel_enabled") == "on",
                    health_change_alert=request.form.get("hdsentinel_health_change_alert") == "on",
                )
                hdsentinel_settings = get_hdsentinel_settings(services.config_manager)
                # Refresh after saving so the page immediately shows the new monitor state.
                hdsentinel_snapshot = collect_hdsentinel_snapshot(
                    services.config_manager,
                    services.system_utils,
                    runtime=services.runtime,
                )
                settings_message = "HDSentinel settings saved successfully."
            except Exception as exc:
                settings_error = f"Failed to save HDSentinel settings: {exc}"
        else:
            smart, missing_attrs, smart_error = get_smart_attributes(
                services.config_manager,
                services.system_utils,
                runtime=services.runtime,
            )
            if smart is None:
                if smart_error == SMARTCTL_JSON_UPGRADE_MESSAGE:
                    smart_support_warning = smart_error
                    error = smart_error
                else:
                    error = smart_error or "Could not retrieve SMART data"
            else:
                prob = predict_failure_probability(smart, runtime=services.runtime)
                if prob is not None:
                    prediction = int(prob >= get_optimal_threshold(services.runtime))
                    probability = prob
                    append_telemetry(smart, prediction, runtime=services.runtime)
                else:
                    error = "Model not loaded"

            if hdsentinel_settings["enabled"]:
                hdsentinel_snapshot = collect_hdsentinel_snapshot(
                    services.config_manager,
                    services.system_utils,
                    runtime=services.runtime,
                )
            # The Drive Health page already did the live probe above, so reuse
            # that result instead of waking or querying the drive a second time.
            summary = {
                "status": "unknown",
                "source": "live",
                "checked_at": datetime.now().isoformat(timespec="seconds"),
                "probability": probability,
                "temperature": smart.get("smart_194_raw") if smart else None,
                "hdsentinel_health": None,
                "hdsentinel_performance": None,
                "detail": error or "Drive health data is not available.",
                "error": error,
            }
            if probability is not None:
                summary["status"] = (
                    "good" if probability < get_optimal_threshold(services.runtime) else "warning"
                )
                summary["detail"] = "SMART prediction completed."
            if hdsentinel_snapshot and hdsentinel_snapshot.get("available"):
                summary["hdsentinel_health"] = hdsentinel_snapshot.get("health_pct")
                summary["hdsentinel_performance"] = hdsentinel_snapshot.get("performance_pct")
                if summary["temperature"] is None:
                    summary["temperature"] = hdsentinel_snapshot.get("temperature_c")
            services.drive_health_summary_service.publish(summary)

    return render_template(
        "drive_health.html",
        smart=smart,
        prediction=prediction,
        probability=probability,
        error=error,
        missing_attrs=missing_attrs,
        smart_fields=SMART_FIELDS,
        hdsentinel_settings=hdsentinel_settings,
        hdsentinel_snapshot=hdsentinel_snapshot,
        drive_config=drive_config,
        smart_support_warning=smart_support_warning,
        settings_message=settings_message,
        settings_error=settings_error,
    )


@drive_health.route("/download_telemetry")
@admin_required
def download_telemetry():
    services = _get_services()
    if services.runtime.telemetry_path.exists():
        return send_file(services.runtime.telemetry_path, as_attachment=True)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return json_problem(
            NotFoundProblem(
                "Telemetry has not been generated yet. Run a health check first.",
                title="Telemetry not found",
                slug="drive-health-telemetry-not-found",
            )
        )
    abort(404)


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
                "probability": None,
                "temperature": None,
                "hdsentinel_health": None,
                "hdsentinel_performance": None,
                "detail": "Drive health summary is unavailable.",
                "error": None,
            }
        )


@drive_health.route("/api/drive_health/refresh", methods=["POST"])
@api_admin_required
def api_drive_health_refresh():
    services = _get_services()
    try:
        summary = build_drive_health_summary(
            services.config_manager,
            services.system_utils,
            runtime=services.runtime,
        )
        return json_data(services.drive_health_summary_service.publish(summary))
    except Exception:
        current_app.logger.exception("Drive health refresh failed")
        checked_at = datetime.now().isoformat(timespec="seconds")
        services.drive_health_summary_service.publish(
            {
                "status": "unknown",
                "source": "live",
                "checked_at": checked_at,
                "probability": None,
                "temperature": None,
                "hdsentinel_health": None,
                "hdsentinel_performance": None,
                "detail": "Drive health refresh failed. Check the application logs.",
                "error": "Drive health refresh failed.",
            }
        )
        return json_problem(OperationProblem("Drive health refresh failed."))
