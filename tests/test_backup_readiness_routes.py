from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

from simple_safer_server.routes.backup_readiness import backup_readiness


def _app(tmp_path):
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / "templates"))
    app.config["TESTING"] = True
    app.secret_key = "test-secret"
    smtp_path = tmp_path / "smtp.conf"
    smtp_path.write_text(
        "\n".join(
            [
                "host smtp.example.com",
                "port 587",
                "from sss@example.com",
                "user admin@example.com",
                "password secret",
            ]
        ),
        encoding="utf-8",
    )
    config_manager = MagicMock()
    config_manager.get_all_config.return_value = {
        "backup": {
            "email_address": "admin@example.com",
            "from_address": "sss@example.com",
            "cloud_enabled": "true",
            "cloud_skipped": "false",
            "rclone_dir": "mega:/Backups",
        },
        "storage": {
            "mode": "existing_folder",
            "path": "/srv/backups",
            "storage_id": "storage-id",
        },
        "schedule": {"backup_cloud_time": "03:00", "configured": "true"},
    }
    smb_manager = MagicMock()
    smb_manager.list_managed_shares.return_value = [
        {"name": "backup", "path": "/srv/backups", "managed": True}
    ]
    app.extensions["simple_safer_server"] = SimpleNamespace(
        config_manager=config_manager,
        runtime=SimpleNamespace(smtp_config_path=smtp_path),
        smb_manager=smb_manager,
    )
    app.register_blueprint(backup_readiness)
    return app


def test_backup_readiness_api_returns_shared_checklist(tmp_path):
    app = _app(tmp_path)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with (
        patch("simple_safer_server.services.user_manager.UserManager", return_value=user_manager),
        app.test_client() as client,
    ):
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.get("/api/backup-readiness")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["status"] == "complete"
    assert payload["data"]["count_label"] == "5 of 5 complete"
    assert [item["key"] for item in payload["data"]["items"]] == [
        "storage",
        "network_access",
        "cloud_backup",
        "alerts",
        "schedule",
    ]
    assert {item["status_label"] for item in payload["data"]["items"]} == {"Complete"}


def test_backup_readiness_fragment_returns_shared_panel(tmp_path):
    app = _app(tmp_path)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with (
        patch("simple_safer_server.services.user_manager.UserManager", return_value=user_manager),
        app.test_client() as client,
    ):
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.get("/fragments/backup-readiness")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Backup protection" in html
    assert 'hx-get="/fragments/backup-readiness"' in html
    assert "5 of 5 complete" in html
