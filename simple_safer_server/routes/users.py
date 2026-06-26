from typing import Any

from flask import Blueprint, current_app, render_template, session

from simple_safer_server.services.user_manager import admin_required, api_admin_required
from simple_safer_server.web.api import json_data, json_problem, json_request_data
from simple_safer_server.web.i18n import gettext
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


def _users_ui_text() -> dict[str, Any]:
    """Return browser copy used by the Users page script."""
    _ = gettext
    return {
        "roles": {
            "admin": _("Admin"),
            "user": _("User"),
        },
        "dates": {
            "notAvailable": _("N/A"),
            "never": _("Never"),
        },
        "actions": {
            "edit": _("Edit"),
            "delete": _("Delete"),
        },
        "messages": {
            "loadFailure": _("Failed to load users."),
            "selfDelete": _("You cannot delete your own account."),
            "deleteTitle": _("Delete User"),
            "deleteConfirm": _('Are you sure you want to delete user "{username}"?'),
            "deleteSuccess": _('User "{username}" deleted successfully.'),
            "networkError": _("Network error."),
            "usernameExists": _("Username already exists."),
            "addSuccess": _('User "{username}" added successfully.'),
            "addFailure": _("Failed to add user."),
            "updateSuccess": _('User "{username}" updated successfully.'),
            "updateFailure": _("Failed to update user."),
        },
    }


@users.route("/users")
@admin_required
def users_page():
    return render_template(
        "users.html",
        username=session.get("username"),
        users_ui_text=_users_ui_text(),
    )


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
            ValidationProblem(
                gettext("is_admin must be a JSON boolean."),
                slug="user-validation-error",
            )
        )

    if not username or not password:
        return json_problem(
            ValidationProblem(
                gettext("Username and password are required."),
                slug="user-validation-error",
            )
        )

    success, message = user_manager.create_user(username, password, is_admin=is_admin)
    if success:
        return json_data(
            {},
            message=gettext("User {username} added successfully.").format(username=username),
        )
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
            ValidationProblem(
                gettext("is_admin must be a JSON boolean."),
                slug="user-validation-error",
            )
        )

    if username not in user_manager.users:
        return json_problem(
            NotFoundProblem(
                gettext("User not found."),
                title=gettext("User not found"),
                slug="user-not-found",
            )
        )

    if (
        username == session.get("username")
        and is_admin is not None
        and not is_admin
        and user_manager.users[username].get("is_admin", False)
    ):
        return json_problem(
            ValidationProblem(
                gettext("You cannot remove your own admin privileges while logged in."),
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
    return json_data(
        {},
        message=gettext("User {username} updated successfully.").format(username=username),
    )


@users.route("/api/users/<username>", methods=["DELETE"])
@api_admin_required
def api_delete_user(username):
    user_manager = _get_services().user_manager
    user_manager.reload_users()

    if username == session.get("username"):
        return json_problem(
            ValidationProblem(
                gettext("Cannot delete the currently logged-in user."),
                slug="user-validation-error",
            )
        )

    success, message = user_manager.delete_user(username)
    if success:
        return json_data(
            {},
            message=gettext("User {username} deleted successfully.").format(username=username),
        )
    return json_problem(
        ValidationProblem(
            gettext("Failed to delete user {username}: {message}").format(
                username=username,
                message=message,
            ),
            slug="user-validation-error",
        )
    )
