from typing import Any

from flask import Blueprint, current_app, jsonify, render_template, request, session

from simple_safer_server.services.user_manager import admin_required, api_admin_required

users = Blueprint("users_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


@users.route("/users")
@admin_required
def users_page():
    return render_template("users.html", username=session.get("username"))


@users.route("/api/users", methods=["GET"])
@api_admin_required
def api_list_users():
    user_manager = _get_services().user_manager
    user_manager.users = user_manager._load_users()
    response_users = []
    for username, data in user_manager.users.items():
        response_users.append(
            {
                "username": username,
                "is_admin": data.get("is_admin", False),
                "created_at": data.get("created_at"),
                "last_login": data.get("last_login"),
            }
        )
    return jsonify({"success": True, "users": response_users})


@users.route("/api/users", methods=["POST"])
@api_admin_required
def api_add_user():
    user_manager = _get_services().user_manager
    user_manager.users = user_manager._load_users()
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")
    is_admin = data.get("is_admin", False)

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
    user_manager.users = user_manager._load_users()
    data = request.get_json(silent=True) or {}
    new_password = data.get("password")
    is_admin = data.get("is_admin")

    if username not in user_manager.users:
        return jsonify({"success": False, "error": "User not found"}), 404

    if (
        username == session.get("username")
        and is_admin is not None
        and not bool(is_admin)
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
        user_manager.users[username]["is_admin"] = bool(is_admin)

    user_manager._save_users()
    return jsonify({"success": True})


@users.route("/api/users/<username>", methods=["DELETE"])
@api_admin_required
def api_delete_user(username):
    user_manager = _get_services().user_manager
    user_manager.users = user_manager._load_users()

    if username == session.get("username"):
        return jsonify({"error": "Cannot delete the currently logged-in user"}), 400

    success, message = user_manager.delete_user(username)
    if success:
        return jsonify({"success": True, "message": f"User {username} deleted successfully"})
    return jsonify({"error": f"Failed to delete user {username}: {message}"}), 400
