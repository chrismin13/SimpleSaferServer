from typing import Any

from flask import Blueprint, current_app, render_template, session

from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_data, json_problem, json_request_data
from simple_safer_server.web.problems import ApiProblem, OperationProblem

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
        return json_data(_get_services().cloud_backup_service.get_config())
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception as exc:
        current_app.logger.error("Error getting cloud backup config: %s", exc)
        return json_problem(OperationProblem("Could not load backup settings."))


@cloud_backup.route("/api/cloud_backup/config", methods=["POST"])
@api_admin_required
def api_cloud_backup_set_config():
    try:
        data = json_request_data()
        _get_services().cloud_backup_service.save_config(data)
        return json_data({}, message="Backup settings saved.")
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception as exc:
        current_app.logger.error("Error saving cloud backup config: %s", exc)
        return json_problem(OperationProblem("Could not save backup settings."))


@cloud_backup.route("/api/cloud_backup/status", methods=["GET"])
@api_admin_required
def api_cloud_backup_status():
    try:
        return json_data(_get_services().cloud_backup_service.get_status())
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception as exc:
        current_app.logger.error("Error getting cloud backup status: %s", exc)
        return json_problem(OperationProblem("Could not get backup status."))


@cloud_backup.route("/api/cloud_backup/run", methods=["POST"])
@api_admin_required
def api_cloud_backup_run():
    try:
        _get_services().cloud_backup_service.run_backup()
        return json_data({}, message="Cloud backup started.")
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception as exc:
        current_app.logger.error("Error running cloud backup: %s", exc)
        return json_problem(OperationProblem("Could not start backup."))


@cloud_backup.route("/api/cloud_backup/mega/list_folders", methods=["POST"])
@api_admin_required
def api_cloud_backup_mega_list_folders():
    try:
        data = json_request_data()
        return json_data(_get_services().cloud_backup_service.list_mega_folders(data))
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception as exc:
        current_app.logger.error("Error listing MEGA folders: %s", exc)
        return json_problem(OperationProblem("Could not list MEGA folders."))


@cloud_backup.route("/api/cloud_backup/mega/create_folder", methods=["POST"])
@api_admin_required
def api_cloud_backup_mega_create_folder():
    try:
        data = json_request_data()
        _get_services().cloud_backup_service.create_mega_folder(data)
        return json_data({}, message="Folder created.")
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception as exc:
        current_app.logger.error("Error creating MEGA folder: %s", exc)
        return json_problem(OperationProblem("Could not create MEGA folder."))


@cloud_backup.route("/api/cloud_backup/schedule", methods=["GET"])
@api_admin_required
def api_cloud_backup_get_schedule():
    try:
        return json_data(_get_services().cloud_backup_service.get_schedule())
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception as exc:
        current_app.logger.error("Error getting backup schedule: %s", exc)
        return json_problem(OperationProblem("Could not load backup settings."))


@cloud_backup.route("/api/cloud_backup/schedule", methods=["POST"])
@api_admin_required
def api_cloud_backup_set_schedule():
    try:
        data = json_request_data()
        _get_services().cloud_backup_service.save_schedule(data)
        return json_data({}, message="Backup settings saved.")
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception as exc:
        current_app.logger.error("Error saving backup schedule: %s", exc)
        return json_problem(OperationProblem("Could not save backup settings."))


@cloud_backup.route("/api/cloud_backup/mega/validate", methods=["POST"])
@api_admin_required
def api_cloud_backup_mega_validate():
    try:
        data = json_request_data()
        _get_services().cloud_backup_service.validate_mega(data)
        return json_data({}, message="MEGA credentials validated.")
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception as exc:
        current_app.logger.error("Error validating MEGA credentials: %s", exc)
        return json_problem(OperationProblem("Could not validate MEGA credentials."))
