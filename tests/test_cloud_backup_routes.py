from pathlib import Path
from tempfile import mkdtemp
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from simple_safer_server.modules.cloud_backup.routes import cloud_backup


def _services():
    return SimpleNamespace(
        runtime=SimpleNamespace(data_dir=Path(mkdtemp(prefix="sss-cloud-backup-test-")), is_fake=True),
        cloud_backup_service=MagicMock(),
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
    app.register_blueprint(cloud_backup)
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


def _admin_post(app, path, payload=None):
    client = app.test_client()
    with client.session_transaction() as session:
        session["username"] = "admin"
    with patch(
        "simple_safer_server.services.user_manager.UserManager",
        return_value=SimpleNamespace(is_admin=lambda username: username == "admin"),
    ):
        return client.post(path, json=payload or {})


def test_cloud_backup_page_renders_module_owned_help():
    app = _app_with_services(_services())

    response = _admin_get(app, "/cloud_backup")

    assert response.status_code == 200
    assert b"<wa-callout" in response.data
    assert b"module-help-band" in response.data
    assert b"Cloud Backup gives the server an off-site copy of backup data" in response.data
    assert b"Configure rclone with an SSS-owned config" in response.data
    assert b"Cloud sync can delete remote files" in response.data
    assert b'data-module-help-key="backup_time"' in response.data
    assert b"The daily time when the worker should run the cloud backup." in response.data
    assert b'data-module-help-key="rclone_config"' in response.data
    assert b"SSS stores it in its own config path." in response.data


def test_cloud_backup_page_renders_route_owned_browser_copy():
    app = _app_with_services(_services())

    response = _admin_get(app, "/cloud_backup")

    assert response.status_code == 200
    assert b'id="cloud-backup-copy"' in response.data
    assert b"Could not load backup status." in response.data
    assert b"Cloud backup settings saved successfully." in response.data
    assert b"Could not load folders." in response.data
    assert b"MEGA credentials are required before creating a folder." in response.data
    assert b"timepicker.js" not in response.data


@pytest.mark.parametrize(
    ("path", "payload", "service_method"),
    (
        (
            "/api/cloud_backup/config",
            {"cloud_enabled": "false"},
            "save_config",
        ),
        (
            "/api/cloud_backup/schedule",
            {"backup_cloud_time": "04:00", "bandwidth_limit": "4M"},
            "save_schedule",
        ),
        ("/api/cloud_backup/run", {}, "run_backup"),
        (
            "/api/cloud_backup/mega/create_folder",
            {"path": "/", "folder_name": "Backups"},
            "create_mega_folder",
        ),
    ),
)
def test_cloud_backup_write_routes_require_module_apply(path, payload, service_method):
    services = _services()
    app = _app_with_services(services)

    response = _admin_post(app, path, payload)

    assert response.status_code == 409
    assert response.get_json()["type"].endswith("#module-setup-required")
    getattr(services.cloud_backup_service, service_method).assert_not_called()
