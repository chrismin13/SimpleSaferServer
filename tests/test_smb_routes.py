from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from simple_safer_server.routes.smb import smb


def _app():
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["TESTING"] = True
    app.extensions["simple_safer_server"] = SimpleNamespace()
    app.register_blueprint(smb)
    app.add_url_rule("/login", "login", lambda: "login")
    return app


def _admin_get(app, path):
    client = app.test_client()
    with client.session_transaction() as session:
        session["username"] = "admin"
    with patch(
        "simple_safer_server.services.user_manager.UserManager",
        return_value=SimpleNamespace(is_admin=lambda username: username == "admin"),
    ):
        return client.get(path)


def test_list_dirs_keeps_dirs_field_and_adds_file_entries(tmp_path):
    app = _app()
    (tmp_path / "share").mkdir()
    (tmp_path / "readme.txt").write_text("hello", encoding="utf-8")

    response = _admin_get(app, f"/api/list_dirs?path={tmp_path}")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["dirs"] == ["share"]
    assert payload["files"] == ["readme.txt"]
    assert payload["entries"] == [
        {"name": "share", "type": "folder"},
        {"name": "readme.txt", "type": "file"},
    ]
