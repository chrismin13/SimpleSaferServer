from typing import Any

from flask import Blueprint, current_app, jsonify, render_template, request, session

from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_error, json_success

cloud_backup = Blueprint("cloud_backup_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


@cloud_backup.route("/cloud_backup")
@admin_required
def cloud_backup_page():
    return render_template("cloud_backup.html", username=session.get("username"))


@cloud_backup.route("/api/cloud_backup/config", methods=["GET"])
@api_admin_required
def api_cloud_backup_get_config():
    try:
        return json_success(config=_get_services().cloud_backup_service.get_config())
    except Exception as exc:
        current_app.logger.error("Error getting cloud backup config: %s", exc)
        return json_error("Could not load backup settings.", status_code=500)


@cloud_backup.route("/api/cloud_backup/config", methods=["POST"])
@api_admin_required
def api_cloud_backup_set_config():
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return json_error("Request body must be a JSON object.", status_code=400)
        return jsonify(_get_services().cloud_backup_service.save_config(data))
    except Exception as exc:
        current_app.logger.error("Error saving cloud backup config: %s", exc)
        return json_error("Could not save backup settings.", status_code=500)


@cloud_backup.route("/api/cloud_backup/status", methods=["GET"])
@api_admin_required
def api_cloud_backup_status():
    try:
        return jsonify(_get_services().cloud_backup_service.get_status())
    except Exception as exc:
        current_app.logger.error("Error getting cloud backup status: %s", exc)
        return json_error("Could not get backup status.", status_code=500)


@cloud_backup.route("/api/cloud_backup/run", methods=["POST"])
@api_admin_required
def api_cloud_backup_run():
    try:
        return jsonify(_get_services().cloud_backup_service.run_backup())
    except Exception as exc:
        current_app.logger.error("Error running cloud backup: %s", exc)
        return json_error("Could not start backup.", status_code=500)


@cloud_backup.route("/api/cloud_backup/mega/list_folders", methods=["POST"])
@api_admin_required
def api_cloud_backup_mega_list_folders():
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return json_error("Request body must be a JSON object.", status_code=400)
        return jsonify(_get_services().cloud_backup_service.list_mega_folders(data))
    except Exception as exc:
        current_app.logger.error("Error listing MEGA folders: %s", exc)
        return json_error("Could not list MEGA folders.", status_code=500)


@cloud_backup.route("/api/cloud_backup/mega/create_folder", methods=["POST"])
@api_admin_required
def api_cloud_backup_mega_create_folder():
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return json_error("Request body must be a JSON object.", status_code=400)
        return jsonify(_get_services().cloud_backup_service.create_mega_folder(data))
    except Exception as exc:
        current_app.logger.error("Error creating MEGA folder: %s", exc)
        return json_error("Could not create MEGA folder.", status_code=500)


@cloud_backup.route("/api/cloud_backup/schedule", methods=["GET"])
@api_admin_required
def api_cloud_backup_get_schedule():
    try:
        return jsonify(_get_services().cloud_backup_service.get_schedule())
    except Exception as exc:
        current_app.logger.error("Error getting backup schedule: %s", exc)
        return json_error("Could not load backup settings.", status_code=500)


@cloud_backup.route("/api/cloud_backup/schedule", methods=["POST"])
@api_admin_required
def api_cloud_backup_set_schedule():
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return json_error("Request body must be a JSON object.", status_code=400)
        return jsonify(_get_services().cloud_backup_service.save_schedule(data))
    except Exception as exc:
        current_app.logger.error("Error saving backup schedule: %s", exc)
        return json_error("Could not save backup settings.", status_code=500)


@cloud_backup.route("/api/cloud_backup/mega/validate", methods=["POST"])
@api_admin_required
def api_cloud_backup_mega_validate():
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return json_error("Request body must be a JSON object.", status_code=400)
        return jsonify(_get_services().cloud_backup_service.validate_mega(data))
    except Exception as exc:
        current_app.logger.error("Error validating MEGA credentials: %s", exc)
        return json_error("Could not validate MEGA credentials.", status_code=500)
