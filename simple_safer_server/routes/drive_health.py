from typing import Any

from flask import Blueprint, abort, jsonify, render_template, request, send_file

from simple_safer_server.services.drive_health import (
    SMART_FIELDS,
    SMARTCTL_JSON_UPGRADE_MESSAGE,
    append_telemetry,
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
        smartctl_json_supported, smartctl_json_error = get_smartctl_json_support()
        if not smartctl_json_supported:
            smart_support_warning = smartctl_json_error

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
        return jsonify(
            {
                "success": False,
                "error": "Telemetry has not been generated yet. Run a health check first.",
            }
        ), 404
    abort(404)


@drive_health.route("/api/drive_health/summary")
@api_admin_required
def api_drive_health_summary():
    services = _get_services()
    try:
        smart, _missing_attrs, smart_error = get_smart_attributes(
            services.config_manager,
            services.system_utils,
            runtime=services.runtime,
        )
        if smart is None:
            return jsonify(
                {
                    "status": "unknown",
                    "probability": None,
                    "temperature": None,
                    "error": smart_error,
                }
            )
        prob = predict_failure_probability(smart, runtime=services.runtime)
        if prob is not None:
            temperature = smart.get("smart_194_raw", None)
            status = "good" if prob < get_optimal_threshold(services.runtime) else "warning"
            response = {
                "status": status,
                "probability": prob,
                "temperature": temperature,
            }
            hdsentinel_snapshot = get_hdsentinel_display_snapshot(
                services.config_manager,
                services.system_utils,
                runtime=services.runtime,
            )
            hdsentinel_settings = get_hdsentinel_settings(services.config_manager)
            if isinstance(hdsentinel_settings, dict):
                hdsentinel_enabled = bool(hdsentinel_settings.get("enabled"))
            else:
                hdsentinel_enabled = bool(getattr(hdsentinel_settings, "enabled", False))
            if hdsentinel_enabled and hdsentinel_snapshot and hdsentinel_snapshot.get("available"):
                response["hdsentinel_health"] = hdsentinel_snapshot.get("health_pct")
                response["hdsentinel_performance"] = hdsentinel_snapshot.get("performance_pct")
            return jsonify(response)
        return jsonify({"status": "unknown", "probability": None, "temperature": None})
    except Exception:
        return jsonify({"status": "unknown", "probability": None, "temperature": None})
