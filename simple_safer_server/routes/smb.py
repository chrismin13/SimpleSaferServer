import os
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from simple_safer_server.services.smb_manager import SMB_DOCS_URL
from simple_safer_server.services.user_manager import api_admin_required

smb = Blueprint("smb_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


def _invalid_share_name(name: str) -> bool:
    return " " in name or any(
        char in name for char in ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]
    )


@smb.route("/api/smb/shares", methods=["GET"])
@api_admin_required
def api_list_smb_shares():
    try:
        manager = _get_services().smb_manager
        shares = manager.list_managed_shares()
        unmanaged_shares = manager.list_unmanaged_shares()
        return jsonify(
            {
                "shares": shares,
                "unmanaged_shares_detected": bool(unmanaged_shares),
                "unmanaged_share_count": len(unmanaged_shares),
                "unmanaged_share_names": [share["name"] for share in unmanaged_shares],
            }
        )
    except Exception as exc:
        current_app.logger.error("Error reading SMB shares: %s", exc)
        return jsonify({"error": "Failed to read SMB shares"}), 500


@smb.route("/api/smb/shares", methods=["POST"])
@api_admin_required
def api_add_smb_share():
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "JSON object is required"}), 400
        share_name = data.get("name", "").strip()
        path = data.get("path", "").strip()
        writable = data.get("writable", False)
        comment = data.get("comment", "").strip()
        valid_users = data.get("valid_users", [])

        if not share_name or not path:
            return jsonify({"error": "Share name and path are required"}), 400
        if _invalid_share_name(share_name):
            return jsonify({"error": "Share name contains invalid characters"}), 400

        _get_services().smb_manager.create_managed_share(
            share_name, path, writable, comment, valid_users
        )
        return jsonify({"message": f"Share {share_name} added successfully"})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.error("Error adding SMB share: %s", exc)
        return jsonify({"error": "Failed to add SMB share"}), 500


@smb.route("/api/smb/shares/<share_name>", methods=["PUT"])
@api_admin_required
def api_edit_smb_share(share_name):
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "JSON object is required"}), 400
        new_name = data.get("name", "").strip()
        path = data.get("path", "").strip()
        writable = data.get("writable", False)
        comment = data.get("comment", "").strip()
        valid_users = data.get("valid_users", [])

        if not new_name or not path:
            return jsonify({"error": "Share name and path are required"}), 400
        if _invalid_share_name(new_name):
            return jsonify({"error": "Share name contains invalid characters"}), 400

        _get_services().smb_manager.update_managed_share(
            share_name, new_name, path, writable, comment, valid_users
        )
        return jsonify({"message": f"Share {share_name} updated successfully"})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.error("Error editing SMB share: %s", exc)
        return jsonify({"error": "Failed to edit SMB share"}), 500


@smb.route("/api/smb/shares/<share_name>", methods=["DELETE"])
@api_admin_required
def api_delete_smb_share(share_name):
    try:
        _get_services().smb_manager.delete_managed_share(share_name)
        return jsonify({"message": f"Share {share_name} deleted successfully"})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.error("Error deleting SMB share: %s", exc)
        return jsonify({"error": "Failed to delete SMB share"}), 500


@smb.route("/api/smb/status")
@api_admin_required
def api_smb_status():
    try:
        return jsonify(_get_services().smb_manager.get_service_status())
    except Exception as exc:
        current_app.logger.error("Error getting SMB status: %s", exc)
        return jsonify({"error": "Failed to get SMB status"}), 500


@smb.route("/api/smb/restart", methods=["POST"])
@api_admin_required
def api_restart_smb():
    try:
        if _get_services().smb_manager._restart_services():
            return jsonify({"message": "SMB services restarted successfully"})
        return jsonify({"error": "Failed to restart SMB services"}), 500
    except Exception as exc:
        current_app.logger.error("Error restarting SMB services: %s", exc)
        return jsonify({"error": "Failed to restart SMB services"}), 500


@smb.route("/api/smb/shares/<share_name>/users", methods=["GET"])
@api_admin_required
def api_get_share_users(share_name):
    try:
        share = _get_services().smb_manager.get_managed_share(share_name)
        if share is None:
            return jsonify(
                {
                    "error": (
                        f"Share {share_name} is not managed by SimpleSaferServer. "
                        f"See {SMB_DOCS_URL} for manual conversion guidance."
                    )
                }
            ), 400
        return jsonify({"users": share.get("valid_users", [])})
    except Exception as exc:
        current_app.logger.error("Error getting share users: %s", exc)
        return jsonify({"error": "Failed to get share users"}), 500


@smb.route("/api/smb/shares/<share_name>/users", methods=["PUT"])
@api_admin_required
def api_update_share_users(share_name):
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "JSON object is required"}), 400
        users = data.get("users", [])
        services = _get_services()
        for username in users:
            if not services.user_manager.get_user(username):
                return jsonify({"error": f"User {username} does not exist"}), 400

        services.smb_manager.update_share_users(share_name, users)
        return jsonify({"message": f"Share {share_name} users updated successfully"})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.error("Error updating share users: %s", exc)
        return jsonify({"error": "Failed to update share users"}), 500


@smb.route("/api/list_dirs", methods=["GET"])
@api_admin_required
def api_list_dirs():
    path = os.path.abspath(request.args.get("path", "/"))
    try:
        if not os.path.isdir(path):
            return jsonify({"error": "Not a directory"}), 400
        entries = []
        for entry in os.listdir(path):
            full_path = os.path.join(path, entry)
            if os.path.isdir(full_path):
                entries.append(entry)
        entries.sort()
        parent = os.path.dirname(path) if path != "/" else None
        return jsonify({"path": path, "parent": parent, "dirs": entries})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
