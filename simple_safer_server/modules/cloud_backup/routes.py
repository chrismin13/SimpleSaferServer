from typing import Any

from flask import Blueprint, current_app, render_template, session

from simple_safer_server.core.module_lifecycle import (
    ModuleLifecycleError,
    require_module_applied,
)
from simple_safer_server.modules.cloud_backup.module import (
    create_module as create_cloud_backup_module,
)
from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_data, json_problem, json_request_data
from simple_safer_server.web.i18n import gettext
from simple_safer_server.web.problems import ApiProblem, ConflictProblem, OperationProblem

cloud_backup = Blueprint("cloud_backup_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


def _require_cloud_backup_setup() -> None:
    services = _get_services()
    require_module_applied(create_cloud_backup_module(), services.runtime)


def _module_setup_problem(error: ModuleLifecycleError):
    return json_problem(
        ConflictProblem(
            str(error),
            title=gettext("Module setup required"),
            slug="module-setup-required",
        )
    )


def _cloud_backup_ui_text() -> dict[str, Any]:
    """Return browser copy used by the Cloud Backup page script."""
    _ = gettext
    return {
        "status": {
            "success": _("Success"),
            "failure": _("Failure"),
            "running": _("Running"),
            "missing": _("Missing"),
            "notRunYet": _("Not Run Yet"),
            "error": _("Error"),
            "dash": _("—"),
        },
        "messages": {
            "loadStatusFailure": _("Could not load backup status."),
            "runStarted": _("Cloud backup started."),
            "runFailure": _("Could not start backup."),
            "loadScheduleFailure": _("Could not load schedule."),
            "scheduleSaved": _("Backup settings saved successfully."),
            "saveScheduleFailure": _("Could not save schedule."),
            "credentialsValidated": _("Connection successful. You are signed in."),
            "validateCredentialsFailure": _("Could not validate credentials."),
            "loadConfigFailure": _("Could not load backup settings."),
            "configSaved": _("Cloud backup settings saved successfully."),
            "saveConfigFailure": _("Could not save backup settings."),
        },
        "folderPicker": {
            "loading": _("Loading..."),
            "emptyMessage": _("No subfolders in this directory."),
            "credentialsRequired": _("MEGA credentials are required before creating a folder."),
            "loadFailed": _("Could not load folders."),
            "createFailed": _("Error creating folder."),
        },
    }


@cloud_backup.route("/cloud_backup")
@admin_required
def cloud_backup_page():
    return render_template(
        "cloud_backup.html",
        username=session.get("username"),
        cloud_backup_module=create_cloud_backup_module(),
        cloud_backup_ui_text=_cloud_backup_ui_text(),
    )


@cloud_backup.route("/api/cloud_backup/config", methods=["GET"])
@api_admin_required
def api_cloud_backup_get_config():
    try:
        return json_data(_get_services().cloud_backup_service.get_config())
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception as exc:
        current_app.logger.error("Error getting cloud backup config: %s", exc)
        return json_problem(OperationProblem(gettext("Could not load backup settings.")))


@cloud_backup.route("/api/cloud_backup/config", methods=["POST"])
@api_admin_required
def api_cloud_backup_set_config():
    try:
        data = json_request_data()
        _require_cloud_backup_setup()
        _get_services().cloud_backup_service.save_config(data)
        return json_data({}, message=gettext("Backup settings saved."))
    except ModuleLifecycleError as exc:
        return _module_setup_problem(exc)
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception as exc:
        current_app.logger.error("Error saving cloud backup config: %s", exc)
        return json_problem(OperationProblem(gettext("Could not save backup settings.")))


@cloud_backup.route("/api/cloud_backup/status", methods=["GET"])
@api_admin_required
def api_cloud_backup_status():
    try:
        return json_data(_get_services().cloud_backup_service.get_status())
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception as exc:
        current_app.logger.error("Error getting cloud backup status: %s", exc)
        return json_problem(OperationProblem(gettext("Could not get backup status.")))


@cloud_backup.route("/api/cloud_backup/run", methods=["POST"])
@api_admin_required
def api_cloud_backup_run():
    try:
        _require_cloud_backup_setup()
        _get_services().cloud_backup_service.run_backup()
        return json_data({}, message=gettext("Cloud backup started."))
    except ApiProblem as exc:
        return json_problem(exc)
    except ModuleLifecycleError as exc:
        return _module_setup_problem(exc)
    except Exception as exc:
        current_app.logger.error("Error running cloud backup: %s", exc)
        return json_problem(OperationProblem(gettext("Could not start backup.")))


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
        return json_problem(OperationProblem(gettext("Could not list MEGA folders.")))


@cloud_backup.route("/api/cloud_backup/mega/create_folder", methods=["POST"])
@api_admin_required
def api_cloud_backup_mega_create_folder():
    try:
        data = json_request_data()
        _require_cloud_backup_setup()
        _get_services().cloud_backup_service.create_mega_folder(data)
        return json_data({}, message=gettext("Folder created."))
    except ApiProblem as exc:
        return json_problem(exc)
    except ModuleLifecycleError as exc:
        return _module_setup_problem(exc)
    except Exception as exc:
        current_app.logger.error("Error creating MEGA folder: %s", exc)
        return json_problem(OperationProblem(gettext("Could not create MEGA folder.")))


@cloud_backup.route("/api/cloud_backup/schedule", methods=["GET"])
@api_admin_required
def api_cloud_backup_get_schedule():
    try:
        return json_data(_get_services().cloud_backup_service.get_schedule())
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception as exc:
        current_app.logger.error("Error getting backup schedule: %s", exc)
        return json_problem(OperationProblem(gettext("Could not load backup settings.")))


@cloud_backup.route("/api/cloud_backup/schedule", methods=["POST"])
@api_admin_required
def api_cloud_backup_set_schedule():
    try:
        data = json_request_data()
        _require_cloud_backup_setup()
        _get_services().cloud_backup_service.save_schedule(data)
        return json_data({}, message=gettext("Backup settings saved."))
    except ApiProblem as exc:
        return json_problem(exc)
    except ModuleLifecycleError as exc:
        return _module_setup_problem(exc)
    except Exception as exc:
        current_app.logger.error("Error saving backup schedule: %s", exc)
        return json_problem(OperationProblem(gettext("Could not save backup settings.")))


@cloud_backup.route("/api/cloud_backup/mega/validate", methods=["POST"])
@api_admin_required
def api_cloud_backup_mega_validate():
    try:
        data = json_request_data()
        _require_cloud_backup_setup()
        _get_services().cloud_backup_service.validate_mega(data)
        return json_data({}, message=gettext("MEGA credentials validated."))
    except ModuleLifecycleError as exc:
        return _module_setup_problem(exc)
    except ApiProblem as exc:
        return json_problem(exc)
    except Exception as exc:
        current_app.logger.error("Error validating MEGA credentials: %s", exc)
        return json_problem(OperationProblem(gettext("Could not validate MEGA credentials.")))
