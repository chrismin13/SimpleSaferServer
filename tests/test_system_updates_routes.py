from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

from simple_safer_server.routes.system_updates import system_updates


def _build_app(manager):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret"
    app.extensions["simple_safer_server"] = SimpleNamespace(system_updates_manager=manager)
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
