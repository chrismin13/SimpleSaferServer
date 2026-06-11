from typing import Any

from flask import Blueprint, current_app, render_template, session

from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_data, json_problem, json_request_data
from simple_safer_server.web.problems import NotFoundProblem, ValidationProblem

users = Blueprint("users_routes", __name__)


def _get_services() -> Any:
    """Return app-level services registered during Flask startup."""
    return current_app.extensions["simple_safer_server"]


def _optional_admin_flag(data: dict[str, Any], default: bool | None = False) -> bool | None:
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
    return json_data({"users": user_manager.list_users()})


@users.route("/api/users", methods=["POST"])
@api_admin_required
def api_add_user():
    user_manager = _get_services().user_manager
    user_manager.reload_users()
    data = json_request_data()
    username = data.get("username")
    password = data.get("password")
    is_admin = _optional_admin_flag(data, default=False)
    if is_admin is None:
        return json_problem(
            ValidationProblem("is_admin must be a JSON boolean.", slug="user-validation-error")
        )

    if not username or not password:
        return json_problem(
            ValidationProblem("Username and password are required.", slug="user-validation-error")
        )

    success, message = user_manager.create_user(username, password, is_admin=is_admin)
    if success:
        return json_data({}, message=f"User {username} added successfully.")
    return json_problem(ValidationProblem(message, slug="user-validation-error"))


@users.route("/api/users/<username>", methods=["PUT"])
@api_admin_required
def api_edit_user(username):
    user_manager = _get_services().user_manager
    user_manager.reload_users()
    data = json_request_data()
    new_password = data.get("password")
    is_admin = _optional_admin_flag(data, default=None)
    if "is_admin" in data and is_admin is None:
        return json_problem(
            ValidationProblem("is_admin must be a JSON boolean.", slug="user-validation-error")
        )

    if username not in user_manager.users:
        return json_problem(
            NotFoundProblem("User not found.", title="User not found", slug="user-not-found")
        )

    if (
        username == session.get("username")
        and is_admin is not None
        and not is_admin
        and user_manager.users[username].get("is_admin", False)
    ):
        return json_problem(
            ValidationProblem(
                "You cannot remove your own admin privileges while logged in.",
                slug="user-validation-error",
            )
        )

    if new_password:
        success, message = user_manager.set_password(username, new_password)
        if not success:
            return json_problem(ValidationProblem(message, slug="user-validation-error"))

    if is_admin is not None:
        success, message = user_manager.update_admin_status(username, is_admin)
        if not success:
            return json_problem(ValidationProblem(message, slug="user-validation-error"))
    return json_data({}, message=f"User {username} updated successfully.")


@users.route("/api/users/<username>", methods=["DELETE"])
@api_admin_required
def api_delete_user(username):
    user_manager = _get_services().user_manager
    user_manager.reload_users()

    if username == session.get("username"):
        return json_problem(
            ValidationProblem(
                "Cannot delete the currently logged-in user.", slug="user-validation-error"
            )
        )

    success, message = user_manager.delete_user(username)
    if success:
        return json_data({}, message=f"User {username} deleted successfully.")
    return json_problem(
        ValidationProblem(
            f"Failed to delete user {username}: {message}", slug="user-validation-error"
        )
    )
