import os
from typing import Any

from flask import Blueprint, current_app, request

from simple_safer_server.services.smb_manager import SMB_DOCS_URL
from simple_safer_server.services.user_manager import api_admin_required
from simple_safer_server.web.api import json_data, json_problem, json_request_data
from simple_safer_server.web.problems import OperationProblem, ValidationProblem

smb = Blueprint("smb_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


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


@smb.route("/api/smb/shares", methods=["GET"])
@api_admin_required
def api_list_smb_shares():
    try:
        manager = _get_services().smb_manager
        shares = manager.list_managed_shares()
        unmanaged_shares = manager.list_unmanaged_shares()
        return json_data(
            {
                "shares": shares,
                "unmanaged_shares_detected": bool(unmanaged_shares),
                "unmanaged_share_count": len(unmanaged_shares),
                "unmanaged_share_names": [share["name"] for share in unmanaged_shares],
            }
        )
    except Exception as exc:
        current_app.logger.error("Error reading SMB shares: %s", exc)
        return json_problem(OperationProblem("Failed to read SMB shares."))


@smb.route("/api/smb/shares", methods=["POST"])
@api_admin_required
def api_add_smb_share():
    try:
        data = json_request_data()
        share_name = _trimmed_string(data, "name", required=True)
        path = _trimmed_string(data, "path", required=True)
        writable = _validated_writable(data)
        comment = _trimmed_string(data, "comment")
        valid_users = _validated_user_list(data)

        if not share_name or not path:
            return json_problem(
                ValidationProblem("Share name and path are required.", slug="smb-validation-error")
            )
        if _invalid_share_name(share_name):
            return json_problem(
                ValidationProblem(
                    "Share name contains invalid characters.", slug="smb-validation-error"
                )
            )

        _get_services().smb_manager.create_managed_share(
            share_name, path, writable, comment, valid_users
        )
        return json_data({}, message=f"Share {share_name} added successfully.")
    except ValueError as exc:
        return json_problem(ValidationProblem(str(exc), slug="smb-validation-error"))
    except Exception as exc:
        current_app.logger.error("Error adding SMB share: %s", exc)
        return json_problem(
            OperationProblem("Failed to add SMB share.", slug="smb-operation-failed")
        )


@smb.route("/api/smb/shares/<share_name>", methods=["PUT"])
@api_admin_required
def api_edit_smb_share(share_name):
    try:
        data = json_request_data()
        new_name = _trimmed_string(data, "name", required=True)
        path = _trimmed_string(data, "path", required=True)
        writable = _validated_writable(data)
        comment = _trimmed_string(data, "comment")
        valid_users = _validated_user_list(data)

        if not new_name or not path:
            return json_problem(
                ValidationProblem("Share name and path are required.", slug="smb-validation-error")
            )
        if _invalid_share_name(new_name):
            return json_problem(
                ValidationProblem(
                    "Share name contains invalid characters.", slug="smb-validation-error"
                )
            )

        _get_services().smb_manager.update_managed_share(
            share_name, new_name, path, writable, comment, valid_users
        )
        return json_data({}, message=f"Share {share_name} updated successfully.")
    except ValueError as exc:
        return json_problem(ValidationProblem(str(exc), slug="smb-validation-error"))
    except Exception as exc:
        current_app.logger.error("Error editing SMB share: %s", exc)
        return json_problem(
            OperationProblem("Failed to edit SMB share.", slug="smb-operation-failed")
        )


@smb.route("/api/smb/shares/<share_name>", methods=["DELETE"])
@api_admin_required
def api_delete_smb_share(share_name):
    try:
        _get_services().smb_manager.delete_managed_share(share_name)
        return json_data({}, message=f"Share {share_name} deleted successfully.")
    except ValueError as exc:
        return json_problem(ValidationProblem(str(exc), slug="smb-validation-error"))
    except Exception as exc:
        current_app.logger.error("Error deleting SMB share: %s", exc)
        return json_problem(
            OperationProblem("Failed to delete SMB share.", slug="smb-operation-failed")
        )


@smb.route("/api/smb/status")
@api_admin_required
def api_smb_status():
    try:
        return json_data(_get_services().smb_manager.get_service_status())
    except Exception as exc:
        current_app.logger.error("Error getting SMB status: %s", exc)
        return json_problem(
            OperationProblem("Failed to get SMB status.", slug="smb-operation-failed")
        )


@smb.route("/api/smb/restart", methods=["POST"])
@api_admin_required
def api_restart_smb():
    try:
        if _get_services().smb_manager.restart_services():
            return json_data({}, message="SMB services restarted successfully.")
        return json_problem(
            OperationProblem("Failed to restart SMB services.", slug="smb-operation-failed")
        )
    except Exception as exc:
        current_app.logger.error("Error restarting SMB services: %s", exc)
        return json_problem(
            OperationProblem("Failed to restart SMB services.", slug="smb-operation-failed")
        )


@smb.route("/api/smb/shares/<share_name>/users", methods=["GET"])
@api_admin_required
def api_get_share_users(share_name):
    try:
        share = _get_services().smb_manager.get_managed_share(share_name)
        if share is None:
            return json_problem(
                ValidationProblem(
                    f"Share {share_name} is not managed by SimpleSaferServer. "
                    f"See {SMB_DOCS_URL} for manual conversion guidance.",
                    slug="smb-validation-error",
                )
            )
        return json_data({"users": share.get("valid_users", [])})
    except Exception as exc:
        current_app.logger.error("Error getting share users: %s", exc)
        return json_problem(
            OperationProblem("Failed to get share users.", slug="smb-operation-failed")
        )


@smb.route("/api/smb/shares/<share_name>/users", methods=["PUT"])
@api_admin_required
def api_update_share_users(share_name):
    try:
        data = json_request_data()
        users = _validated_user_list(data)
        services = _get_services()
        for username in users:
            if not services.user_manager.get_user(username):
                return json_problem(
                    ValidationProblem(
                        f"User {username} does not exist.", slug="smb-validation-error"
                    )
                )

        services.smb_manager.update_share_users(share_name, users)
        return json_data({}, message=f"Share {share_name} users updated successfully.")
    except ValueError as exc:
        return json_problem(ValidationProblem(str(exc), slug="smb-validation-error"))
    except Exception as exc:
        current_app.logger.error("Error updating share users: %s", exc)
        return json_problem(
            OperationProblem("Failed to update share users.", slug="smb-operation-failed")
        )


@smb.route("/api/list_dirs", methods=["GET"])
@api_admin_required
def api_list_dirs():
    path = os.path.abspath(request.args.get("path", "/"))
    try:
        if not os.path.isdir(path):
            return json_problem(ValidationProblem("Not a directory."))
        entries = []
        for entry in os.listdir(path):
            full_path = os.path.join(path, entry)
            if os.path.isdir(full_path):
                entries.append(entry)
        entries.sort()
        parent = os.path.dirname(path) if path != "/" else None
        return json_data({"path": path, "parent": parent, "dirs": entries})
    except Exception:
        current_app.logger.exception("Error listing directories")
        return json_problem(OperationProblem("Could not list folders for that path."))
