from pathlib import Path
from tempfile import mkdtemp
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

from simple_safer_server.modules.alerts.routes import alerts


def _services():
    return SimpleNamespace(
        runtime=SimpleNamespace(data_dir=Path(mkdtemp(prefix="sss-alerts-test-")), is_fake=True),
        alerts_service=MagicMock(),
    )


def _app_with_services(services):
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / "templates"))
    app.secret_key = "test-secret"
    app.config["TESTING"] = True
    app.extensions["simple_safer_server"] = services
    app.context_processor(
        lambda: {
            "browser_title": lambda page_name: page_name,
            "runtime_mode": "fake",
            "sidebar_nav_items": [],
            "default_mount_point": "/media/backup",
            "is_admin": True,
        }
    )
    app.add_url_rule("/logout", "logout", lambda: "logout")
    app.register_blueprint(alerts)
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


def _admin_post(app, path, json=None):
    client = app.test_client()
    with client.session_transaction() as session:
        session["username"] = "admin"
    with patch(
        "simple_safer_server.services.user_manager.UserManager",
        return_value=SimpleNamespace(is_admin=lambda username: username == "admin"),
    ):
        return client.post(path, json=json)


def test_alerts_page_renders_module_owned_help():
    app = _app_with_services(_services())

    response = _admin_get(app, "/alerts")

    assert response.status_code == 200
    assert b"<wa-callout" in response.data
    assert b"module-help-band" in response.data
    assert b"Alerts tell you when backups or storage checks fail" in response.data
    assert b"Configure email alerts so backup failures are not silent" in response.data
    assert b"Without alerts, backup failures may go unnoticed" in response.data
    assert b'data-module-help-key="email_address"' in response.data
    assert b"Where SSS sends backup, storage, and health warnings." in response.data
    assert b'data-module-help-key="smtp_password"' in response.data
    assert b"Use an app password when your mail provider supports one." in response.data
    assert b'id="alerts-copy"' in response.data
    assert b"Email configuration saved successfully." in response.data
    assert b"Network error while clearing alerts." in response.data


def test_alerts_generate_test_returns_route_owned_message():
    services = _services()
    app = _app_with_services(services)

    response = _admin_post(app, "/api/alerts/generate-test")

    assert response.status_code == 200
    assert response.get_json()["message"] == "Test alerts generated."
    services.alerts_service.generate_test_alerts.assert_called_once_with()
