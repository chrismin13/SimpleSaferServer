from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

from simple_safer_server.routes.system_updates import system_updates
from simple_safer_server.services.app_updates import AppUpdateError


def _build_app(manager):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret"
    app.extensions["simple_safer_server"] = SimpleNamespace(
        system_updates_manager=manager,
        app_update_manager=MagicMock(),
        task_service=MagicMock(),
    )
    app.register_blueprint(system_updates)
    return app


def test_livepatch_setup_returns_validation_problem_for_empty_token():
    manager = MagicMock()
    manager.setup_livepatch.side_effect = ValueError("Livepatch token is required.")
    app = _build_app(manager)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with patch(
        "simple_safer_server.services.user_manager.UserManager", return_value=user_manager
    ), app.test_client() as client:
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.post("/api/system_updates/livepatch/setup", json={"token": ""})

    assert response.status_code == 400
    assert response.get_json() == {
        "type": (
            "https://github.com/chrismin13/SimpleSaferServer/blob/main/"
            "docs/api_responses.md#validation-error"
        ),
        "title": "Validation error",
        "status": 400,
        "detail": "Livepatch token is required.",
    }
    manager.setup_livepatch.assert_called_once_with("")


def test_application_update_returns_conflict_when_no_update_is_available():
    manager = MagicMock()
    app_update_manager = MagicMock()
    app_update_manager.get_status.return_value = {
        "can_update": False,
        "message": "Up to date with origin/main.",
    }
    app = _build_app(manager)
    app.extensions["simple_safer_server"].app_update_manager = app_update_manager
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with patch(
        "simple_safer_server.services.user_manager.UserManager", return_value=user_manager
    ), app.test_client() as client:
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.post("/api/system_updates/application/update")

    assert response.status_code == 409
    assert response.get_json()["detail"] == "Up to date with origin/main."


def test_application_force_update_returns_diagnostic_without_scary_ui_detail():
    manager = MagicMock()
    app_update_manager = MagicMock()
    app_update_manager.get_status.return_value = {
        "can_force_update": True,
        "message": "Changed app files are blocking the update.",
    }
    app_update_manager.force_update_now.side_effect = AppUpdateError(
        "Command: git pull\nstderr:\nfatal"
    )
    app = _build_app(manager)
    app.extensions["simple_safer_server"].app_update_manager = app_update_manager
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with patch(
        "simple_safer_server.services.user_manager.UserManager", return_value=user_manager
    ), app.test_client() as client:
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.post("/api/system_updates/application/force_update")

    payload = response.get_json()
    assert response.status_code == 500
    assert payload["detail"] == "Application cleanup update failed. Check logs before retrying."
    assert payload["diagnostic"] == "Command: git pull\nstderr:\nfatal"
