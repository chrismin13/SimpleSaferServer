from typing import Any, Dict, Optional, Tuple

from flask import Blueprint, Response, current_app, jsonify, render_template, request, session

from simple_safer_server.services.user_manager import admin_required, api_admin_required

users = Blueprint("users_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


JsonResponse = Tuple[Response, int]


def _json_object_payload() -> Tuple[Optional[Dict[str, Any]], Optional[JsonResponse]]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, (
            jsonify({"success": False, "error": "Request body must be a JSON object"}),
            400,
        )
    return data, None


def _optional_admin_flag(data: Dict[str, Any], default: Optional[bool] = False) -> Optional[bool]:
    if "is_admin" not in data:
        return default
    if not isinstance(data["is_admin"], bool):
        return None
    return data["is_admin"]


@users.route("/users")
@admin_required
def users_page():
    return render_template("users.html", username=session.get("username"))


@users.route("/api/users", methods=["GET"])
@api_admin_required
def api_list_users():
    user_manager = _get_services().user_manager
    user_manager.reload_users()
    return jsonify({"success": True, "users": user_manager.list_users()})


@users.route("/api/users", methods=["POST"])
@api_admin_required
def api_add_user():
    user_manager = _get_services().user_manager
    user_manager.reload_users()
    data, error_response = _json_object_payload()
    if error_response:
        return error_response
    if data is None:
        # _json_object_payload returns an error with None; keep a defensive branch
        # so optimized Python cannot remove the route's type narrowing.
        return jsonify({"success": False, "error": "Request body must be a JSON object"}), 400
    username = data.get("username")
    password = data.get("password")
    is_admin = _optional_admin_flag(data, default=False)
    if is_admin is None:
        return jsonify({"success": False, "error": "is_admin must be a JSON boolean"}), 400

    if not username or not password:
        return jsonify({"success": False, "error": "Username and password are required"}), 400

    success, message = user_manager.create_user(username, password, is_admin=is_admin)
    if success:
        return jsonify({"success": True, "error": None})
    return jsonify({"success": False, "error": message}), 400


@users.route("/api/users/<username>", methods=["PUT"])
@api_admin_required
def api_edit_user(username):
    user_manager = _get_services().user_manager
    user_manager.reload_users()
    data, error_response = _json_object_payload()
    if error_response:
        return error_response
    if data is None:
        # _json_object_payload returns an error with None; keep a defensive branch
        # so optimized Python cannot remove the route's type narrowing.
        return jsonify({"success": False, "error": "Request body must be a JSON object"}), 400
    new_password = data.get("password")
    is_admin = _optional_admin_flag(data, default=None)
    if "is_admin" in data and is_admin is None:
        return jsonify({"success": False, "error": "is_admin must be a JSON boolean"}), 400

    if username not in user_manager.users:
        return jsonify({"success": False, "error": "User not found"}), 404

    if (
        username == session.get("username")
        and is_admin is not None
        and not is_admin
        and user_manager.users[username].get("is_admin", False)
    ):
        return jsonify(
            {
                "success": False,
                "error": "You cannot remove your own admin privileges while logged in.",
            }
        ), 400

    if new_password:
        success, message = user_manager.set_password(username, new_password)
        if not success:
            return jsonify({"success": False, "error": message}), 400

    if is_admin is not None:
        success, message = user_manager.update_admin_status(username, is_admin)
        if not success:
            return jsonify({"success": False, "error": message}), 400
    return jsonify({"success": True})


@users.route("/api/users/<username>", methods=["DELETE"])
@api_admin_required
def api_delete_user(username):
    user_manager = _get_services().user_manager
    user_manager.reload_users()

    if username == session.get("username"):
        return jsonify(
            {"success": False, "error": "Cannot delete the currently logged-in user"}
        ), 400

    success, message = user_manager.delete_user(username)
    if success:
        return jsonify({"success": True, "message": f"User {username} deleted successfully"})
    return jsonify({"success": False, "error": f"Failed to delete user {username}: {message}"}), 400
