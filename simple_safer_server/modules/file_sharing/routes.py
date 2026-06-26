from typing import Any

from flask import Blueprint, current_app, render_template, request, session

from simple_safer_server.core.module_lifecycle import ModuleLifecycleError, require_module_applied
from simple_safer_server.core.privileged_client import PrivilegedActionClientError
from simple_safer_server.modules.file_sharing.module import (
    create_module as create_file_sharing_module,
)
from simple_safer_server.modules.file_sharing.service import (
    SMB_DOCS_URL,
    SMBConfigError,
    SMBOperationError,
)
from simple_safer_server.services.filesystem_browser import list_local_path
from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_data, json_problem, json_request_data
from simple_safer_server.web.i18n import gettext
from simple_safer_server.web.problems import ConflictProblem, OperationProblem, ValidationProblem

smb = Blueprint("smb_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


def _require_file_sharing_setup() -> None:
    services = _get_services()
    require_module_applied(create_file_sharing_module(), services.runtime)


def _module_setup_problem(error: ModuleLifecycleError):
    return json_problem(
        ConflictProblem(
            str(error),
            title=gettext("Module setup required"),
            slug="module-setup-required",
        )
    )


def _file_sharing_ui_text() -> dict[str, Any]:
    """Return browser copy used by the File Sharing page script."""
    _ = gettext
    return {
        "folderPicker": {
            "loading": _("Loading..."),
            "emptyMessage": _("No subdirectories."),
            "loadFailed": _("Could not load directories."),
        },
        "serverIdentity": {
            "notSet": _("Not set"),
            "unavailable": _("Unavailable"),
            "confirmTitle": _("Change Server Name"),
            "confirmMessage": _(
                "Change the server name to \"{serverName}\"?\n\n"
                "File sharing discovery will restart, and connected clients may be interrupted briefly."
            ),
            "confirmLabel": _("Save"),
            "updated": _("Server name updated."),
            "updateFailed": _("Failed to update server name"),
        },
        "unmanagedShares": {
            "verificationFailed": _("Unmanaged share verification failed"),
            "verifyFailed": _("Could not verify unmanaged Samba shares."),
            "noneDetected": _("No unmanaged shares detected."),
            "detectedOne": _("{count} unmanaged share detected"),
            "detectedMany": _("{count} unmanaged shares detected"),
        },
        "shares": {
            "loadFailed": _("Failed to load shares"),
            "empty": _("No SimpleSaferServer-managed shares configured"),
            "edit": _("Edit"),
            "delete": _("Delete"),
            "yes": _("Yes"),
            "no": _("No"),
            "dash": _("—"),
            "allUsers": _("All users"),
            "admin": _("Admin"),
            "pathMustStartWithSlash": _("Path must start with /"),
            "addSuccess": _("Share added successfully"),
            "addFailed": _("Failed to add share"),
            "updateSuccess": _("Share updated successfully"),
            "updateFailed": _("Failed to update share"),
            "deleteSuccess": _("Share deleted"),
            "deleteFailed": _("Failed to delete share"),
        },
        "users": {
            "loadFailed": _("Could not load users."),
        },
        "status": {
            "operationalTitle": _("Operational"),
            "operationalMessage": _("File sharing and discovery are working"),
            "partialTitle": _("Partial"),
            "partialMessage": _("File sharing is active, but discovery is incomplete"),
            "downTitle": _("Down"),
            "downMessage": _("File sharing is not running"),
            "errorTitle": _("Error"),
            "errorMessage": _("Unable to check status"),
        },
        "actions": {
            "restartConfirmTitle": _("Restart Services"),
            "restartConfirmMessage": _(
                "Are you sure you want to restart the file sharing services? "
                "Connected clients may be interrupted briefly."
            ),
            "restartConfirmLabel": _("Restart"),
            "restartSuccess": _("Services restarted"),
            "restartFailed": _("Failed to restart"),
        },
    }


def _invalid_share_name(name: str) -> bool:
    return " " in name or any(
        char in name for char in ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]
    )


def _trimmed_string(data, key, required=False):
    value = data.get(key, "")
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    value = value.strip()
    if required and not value:
        raise ValueError(f"{key} is required")
    return value


def _validated_user_list(data):
    users = data.get("users", data.get("valid_users", []))
    if not isinstance(users, list) or not all(isinstance(user, str) for user in users):
        raise ValueError("users must be a JSON array of username strings")
    return users


def _validated_writable(data):
    writable = data.get("writable", False)
    if not isinstance(writable, bool):
        raise ValueError("writable must be a JSON boolean")
    return writable


@smb.route("/network_file_sharing")
@admin_required
def network_file_sharing():
    services = _get_services()
    backup_mount_point = services.config_manager.get_value(
        "backup",
        "mount_point",
        services.runtime.default_mount_point,
    )
    return render_template(
        "network_file_sharing.html",
        username=session.get("username"),
        file_sharing_module=create_file_sharing_module(),
        backup_mount_point=backup_mount_point,
        smb_docs_url=SMB_DOCS_URL,
        file_sharing_ui_text=_file_sharing_ui_text(),
    )


@smb.route("/api/smb/shares", methods=["GET"])
@api_admin_required
def api_list_smb_shares():
    try:
        manager = _get_services().smb_manager
        shares = manager.list_managed_shares()
        unmanaged_shares = []
        unmanaged_shares_verified = True
        unmanaged_share_verification_error = None
        try:
            unmanaged_shares = manager.list_unmanaged_shares()
        except SMBConfigError as exc:
            # Managed-share listing is still useful on page load. Treat only
            # the Effective Samba Config read as unverifiable so the UI can
            # warn without pretending the unmanaged set is empty.
            unmanaged_shares_verified = False
            unmanaged_share_verification_error = str(exc)
        return json_data(
            {
                "shares": shares,
                "unmanaged_shares_verified": unmanaged_shares_verified,
                "unmanaged_shares_detected": bool(unmanaged_shares),
                "unmanaged_share_count": (
                    len(unmanaged_shares) if unmanaged_shares_verified else None
                ),
                "unmanaged_share_names": [share["name"] for share in unmanaged_shares],
                "unmanaged_share_verification_error": unmanaged_share_verification_error,
            }
        )
    except SMBConfigError as exc:
        return json_problem(ValidationProblem(str(exc), slug="smb-validation-error"))
    except Exception as exc:
        current_app.logger.error("Error reading SMB shares: %s", exc)
        return json_problem(OperationProblem(gettext("Failed to read SMB shares.")))


@smb.route("/api/smb/shares", methods=["POST"])
@api_admin_required
def api_add_smb_share():
    try:
        _require_file_sharing_setup()
        data = json_request_data()
        share_name = _trimmed_string(data, "name", required=True)
        path = _trimmed_string(data, "path", required=True)
        writable = _validated_writable(data)
        comment = _trimmed_string(data, "comment")
        valid_users = _validated_user_list(data)

        if not share_name or not path:
            return json_problem(
                ValidationProblem(
                    gettext("Share name and path are required."),
                    slug="smb-validation-error",
                )
            )
        if _invalid_share_name(share_name):
            return json_problem(
                ValidationProblem(
                    gettext("Share name contains invalid characters."),
                    slug="smb-validation-error",
                )
            )

        _get_services().smb_manager.create_managed_share(
            share_name, path, writable, comment, valid_users
        )
        return json_data(
            {},
            message=gettext("Share {share_name} added successfully.").format(
                share_name=share_name
            ),
        )
    except ModuleLifecycleError as exc:
        return _module_setup_problem(exc)
    except ValueError as exc:
        return json_problem(ValidationProblem(str(exc), slug="smb-validation-error"))
    except SMBOperationError as exc:
        return json_problem(OperationProblem(str(exc), slug="smb-operation-failed"))
    except Exception as exc:
        current_app.logger.error("Error adding SMB share: %s", exc)
        return json_problem(
            OperationProblem(gettext("Failed to add SMB share."), slug="smb-operation-failed")
        )


@smb.route("/api/smb/shares/<share_name>", methods=["PUT"])
@api_admin_required
def api_edit_smb_share(share_name):
    try:
        _require_file_sharing_setup()
        data = json_request_data()
        new_name = _trimmed_string(data, "name", required=True)
        path = _trimmed_string(data, "path", required=True)
        writable = _validated_writable(data)
        comment = _trimmed_string(data, "comment")
        valid_users = _validated_user_list(data)

        if not new_name or not path:
            return json_problem(
                ValidationProblem(
                    gettext("Share name and path are required."),
                    slug="smb-validation-error",
                )
            )
        if _invalid_share_name(new_name):
            return json_problem(
                ValidationProblem(
                    gettext("Share name contains invalid characters."),
                    slug="smb-validation-error",
                )
            )

        _get_services().smb_manager.update_managed_share(
            share_name, new_name, path, writable, comment, valid_users
        )
        return json_data(
            {},
            message=gettext("Share {share_name} updated successfully.").format(
                share_name=share_name
            ),
        )
    except ModuleLifecycleError as exc:
        return _module_setup_problem(exc)
    except ValueError as exc:
        return json_problem(ValidationProblem(str(exc), slug="smb-validation-error"))
    except SMBOperationError as exc:
        return json_problem(OperationProblem(str(exc), slug="smb-operation-failed"))
    except Exception as exc:
        current_app.logger.error("Error editing SMB share: %s", exc)
        return json_problem(
            OperationProblem(gettext("Failed to edit SMB share."), slug="smb-operation-failed")
        )


@smb.route("/api/smb/shares/<share_name>", methods=["DELETE"])
@api_admin_required
def api_delete_smb_share(share_name):
    try:
        _require_file_sharing_setup()
        _get_services().smb_manager.delete_managed_share(share_name)
        return json_data(
            {},
            message=gettext("Share {share_name} deleted successfully.").format(
                share_name=share_name
            ),
        )
    except ModuleLifecycleError as exc:
        return _module_setup_problem(exc)
    except ValueError as exc:
        return json_problem(ValidationProblem(str(exc), slug="smb-validation-error"))
    except SMBOperationError as exc:
        return json_problem(OperationProblem(str(exc), slug="smb-operation-failed"))
    except Exception as exc:
        current_app.logger.error("Error deleting SMB share: %s", exc)
        return json_problem(
            OperationProblem(gettext("Failed to delete SMB share."), slug="smb-operation-failed")
        )


@smb.route("/api/smb/status")
@api_admin_required
def api_smb_status():
    try:
        return json_data(_get_services().smb_manager.get_service_status())
    except Exception as exc:
        current_app.logger.error("Error getting SMB status: %s", exc)
        return json_problem(
            OperationProblem(gettext("Failed to get SMB status."), slug="smb-operation-failed")
        )


@smb.route("/api/smb/restart", methods=["POST"])
@api_admin_required
def api_restart_smb():
    try:
        _require_file_sharing_setup()
        result = _get_services().privileged_actions.run("file-sharing.reload", {})
        return json_data(
            {},
            message=result.data.get("message", gettext("SMB services restarted successfully.")),
        )
    except ModuleLifecycleError as exc:
        return _module_setup_problem(exc)
    except PrivilegedActionClientError as exc:
        current_app.logger.error("Privileged SMB reload action failed: %s", exc)
        return json_problem(OperationProblem(str(exc), slug="smb-operation-failed"))
    except Exception as exc:
        current_app.logger.error("Error restarting SMB services: %s", exc)
        return json_problem(
            OperationProblem(
                gettext("Failed to restart SMB services."),
                slug="smb-operation-failed",
            )
        )


@smb.route("/api/smb/shares/<share_name>/users", methods=["GET"])
@api_admin_required
def api_get_share_users(share_name):
    try:
        share = _get_services().smb_manager.get_managed_share(share_name)
        if share is None:
            return json_problem(
                ValidationProblem(
                    gettext(
                        "Share {share_name} is not managed by SimpleSaferServer. "
                        "See {docs_url} for manual conversion guidance."
                    ).format(share_name=share_name, docs_url=SMB_DOCS_URL),
                    slug="smb-validation-error",
                )
            )
        return json_data({"users": share.get("valid_users", [])})
    except Exception as exc:
        current_app.logger.error("Error getting share users: %s", exc)
        return json_problem(
            OperationProblem(gettext("Failed to get share users."), slug="smb-operation-failed")
        )


@smb.route("/api/smb/shares/<share_name>/users", methods=["PUT"])
@api_admin_required
def api_update_share_users(share_name):
    try:
        _require_file_sharing_setup()
        data = json_request_data()
        users = _validated_user_list(data)
        services = _get_services()
        for username in users:
            if not services.user_manager.get_user(username):
                return json_problem(
                    ValidationProblem(
                        gettext("User {username} does not exist.").format(username=username),
                        slug="smb-validation-error",
                    )
                )

        services.smb_manager.update_share_users(share_name, users)
        return json_data(
            {},
            message=gettext("Share {share_name} users updated successfully.").format(
                share_name=share_name
            ),
        )
    except ModuleLifecycleError as exc:
        return _module_setup_problem(exc)
    except ValueError as exc:
        return json_problem(ValidationProblem(str(exc), slug="smb-validation-error"))
    except Exception as exc:
        current_app.logger.error("Error updating share users: %s", exc)
        return json_problem(
            OperationProblem(gettext("Failed to update share users."), slug="smb-operation-failed")
        )


@smb.route("/api/list_dirs", methods=["GET", "POST"])
@api_admin_required
def api_list_dirs():
    try:
        data = json_request_data() if request.method == "POST" else request.args
        return json_data(list_local_path(data.get("path", "/")))
    except NotADirectoryError:
        return json_problem(ValidationProblem(gettext("Not a directory.")))
    except Exception:
        current_app.logger.exception("Error listing directories")
        return json_problem(OperationProblem(gettext("Could not list folders for that path.")))
