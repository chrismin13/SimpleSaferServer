from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

from simple_safer_server.routes.storage import storage


def _app_with_services(services):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["TESTING"] = True
    app.extensions["simple_safer_server"] = services
    app.register_blueprint(storage)
    return app


def _admin_post(app, path, json):
    client = app.test_client()
    with client.session_transaction() as session:
        session["username"] = "admin"
    with patch(
        "simple_safer_server.services.user_manager.UserManager",
        return_value=SimpleNamespace(is_admin=lambda username: username == "admin"),
    ):
        return client.post(path, json=json)


def _services():
    config = {
        "backup": {"cloud_enabled": "false", "mount_point": "/srv/storage"},
        "storage": {"mode": "existing_folder", "path": "/srv/storage", "storage_id": "id"},
        "schedule": {"backup_cloud_time": "03:00"},
    }
    config_manager = MagicMock()
    config_manager.get_all_config.return_value = config
    config_manager.get_value.return_value = "admin"
    system_utils = MagicMock()
    system_utils.create_systemd_config_file.return_value = (True, None)
    system_utils.install_systemd_services_and_timers.return_value = (True, None)
    return SimpleNamespace(
        config_manager=config_manager,
        system_utils=system_utils,
        smb_manager=MagicMock(),
        runtime=SimpleNamespace(is_fake=True, default_mount_point="/media/backup"),
        command_runner=MagicMock(),
    )


def test_existing_folder_storage_refreshes_systemd_timers():
    services = _services()
    app = _app_with_services(services)

    with patch(
        "simple_safer_server.routes.storage.configure_existing_folder",
        return_value=SimpleNamespace(path="/srv/storage"),
    ):
        response = _admin_post(app, "/api/storage/existing-folder", {"path": "/srv/storage"})

    assert response.status_code == 200
    services.system_utils.create_systemd_config_file.assert_called_once_with(
        services.config_manager.get_all_config.return_value
    )
    services.system_utils.install_systemd_services_and_timers.assert_called_once_with(
        services.config_manager.get_all_config.return_value
    )


def test_prepared_drive_storage_refreshes_systemd_timers():
    services = _services()
    services.config_manager.get_all_config.return_value["storage"]["mode"] = "prepared_drive"
    app = _app_with_services(services)

    with patch(
        "simple_safer_server.routes.storage.apply_backup_drive_configuration",
        return_value={"mount_point": "/media/backup"},
    ):
        with patch("simple_safer_server.routes.storage.mark_prepared_drive_storage"):
            response = _admin_post(
                app,
                "/api/backup_drive/configure",
                {"partition": "/dev/sdb1", "mount_point": "/media/backup"},
            )

    assert response.status_code == 200
    services.system_utils.create_systemd_config_file.assert_called_once_with(
        services.config_manager.get_all_config.return_value
    )
    services.system_utils.install_systemd_services_and_timers.assert_called_once_with(
        services.config_manager.get_all_config.return_value
    )


def test_existing_folder_reports_timer_refresh_failure():
    services = _services()
    services.system_utils.install_systemd_services_and_timers.return_value = (
        False,
        "systemd failed",
    )
    app = _app_with_services(services)

    with patch(
        "simple_safer_server.routes.storage.configure_existing_folder",
        return_value=SimpleNamespace(path="/srv/storage"),
    ):
        response = _admin_post(app, "/api/storage/existing-folder", {"path": "/srv/storage"})

    assert response.status_code == 500
    assert "task timers were not refreshed" in response.get_json()["detail"]
