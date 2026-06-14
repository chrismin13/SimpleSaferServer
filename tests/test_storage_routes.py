from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

from simple_safer_server.routes.storage import _build_storage_safety_checks, storage


def _app_with_services(services):
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.secret_key = "test-secret"
    app.config["TESTING"] = True
    app.extensions["simple_safer_server"] = services
    app.jinja_env.globals["browser_title"] = lambda title: title
    app.register_blueprint(storage)
    app.add_url_rule("/login", "login", lambda: "login")
    app.add_url_rule("/", "task_routes.dashboard", lambda: "dashboard")
    app.add_url_rule("/shares", "network_file_sharing", lambda: "shares")
    app.add_url_rule("/users", "users_routes.users_page", lambda: "users")
    app.add_url_rule("/drives", "drive_health_routes.drives", lambda: "drives")
    app.add_url_rule("/ddns", "ddns_routes.ddns_page", lambda: "ddns")
    app.add_url_rule("/cloud-backup", "cloud_backup_routes.cloud_backup_page", lambda: "cloud")
    app.add_url_rule(
        "/system-updates",
        "system_updates_routes.system_updates_page",
        lambda: "updates",
    )
    app.add_url_rule("/alerts", "alerts_routes.alerts_page", lambda: "alerts")
    app.add_url_rule("/logout", "logout", lambda: "logout")
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
        task_service=SimpleNamespace(get_check_mount_next_run=lambda: None),
    )


def test_change_drive_page_requires_admin_session():
    app = _app_with_services(_services())

    response = app.test_client().get("/storage/change-drive")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_change_drive_page_renders_inside_storage_shell():
    app = _app_with_services(_services())

    response = _admin_get(app, "/storage/change-drive")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Change Prepared Drive" in body
    assert "Format a drive" in body
    assert "Use an NTFS partition" in body
    assert "/static/js/storage_change_drive.js" in body


def test_storage_page_links_to_change_prepared_drive_without_scan_action():
    services = _services()
    app = _app_with_services(services)

    with (
        patch(
            "simple_safer_server.routes.storage.get_storage_location",
            return_value=SimpleNamespace(
                mode="prepared_drive",
                path="/media/backup",
                app_manages_mount=True,
            ),
        ),
        patch(
            "simple_safer_server.routes.storage.storage_status",
            return_value={"ok": True, "error": ""},
        ),
    ):
        response = _admin_get(app, "/storage")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Change Prepared Drive" in body
    assert "/storage/change-drive" in body
    assert "Scan Connected Drives" not in body


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


def test_prepared_drive_configure_passes_ntfs_driver():
    services = _services()
    app = _app_with_services(services)

    with patch(
        "simple_safer_server.routes.storage.apply_backup_drive_configuration",
        return_value={"mount_point": "/media/backup"},
    ) as apply_backup_drive_configuration:
        with patch("simple_safer_server.routes.storage.mark_prepared_drive_storage"):
            response = _admin_post(
                app,
                "/api/backup_drive/configure",
                {
                    "partition": "/dev/sdb1",
                    "mount_point": "/media/backup",
                    "ntfs_driver": "ntfs3",
                },
            )

    assert response.status_code == 200
    assert apply_backup_drive_configuration.call_args.kwargs["ntfs_driver"] == "ntfs3"


def test_format_drive_list_uses_broad_scan():
    services = _services()
    app = _app_with_services(services)

    with patch(
        "simple_safer_server.routes.storage.list_available_drives",
        return_value=[{"path": "/dev/sdb", "partitions": []}],
    ) as list_available_drives:
        response = _admin_get(app, "/api/backup_drive/format-drives")

    assert response.status_code == 200
    assert response.get_json()["data"]["drives"][0]["path"] == "/dev/sdb"
    list_available_drives.assert_called_once_with(runtime=services.runtime, ntfs_only=False)


def test_format_drive_requires_disk():
    services = _services()
    app = _app_with_services(services)

    response = _admin_post(app, "/api/backup_drive/format", {})

    assert response.status_code == 400
    assert "No disk selected" in response.get_json()["detail"]


def test_format_drive_failure_returns_validation_problem():
    services = _services()
    app = _app_with_services(services)

    with patch(
        "simple_safer_server.routes.storage.format_backup_drive",
        side_effect=Exception("boom"),
    ):
        response = _admin_post(app, "/api/backup_drive/format", {"disk": "/dev/sdb"})

    assert response.status_code == 500
    assert "Could not format" in response.get_json()["detail"]


def test_format_drive_does_not_mutate_storage_config():
    services = _services()
    app = _app_with_services(services)

    with patch(
        "simple_safer_server.routes.storage.format_backup_drive",
        return_value={
            "disk": "/dev/sdb",
            "partition": "/dev/sdb1",
            "message": "Successfully formatted /dev/sdb1 as NTFS.",
        },
    ):
        response = _admin_post(app, "/api/backup_drive/format", {"disk": "/dev/sdb"})

    assert response.status_code == 200
    services.config_manager.set_value.assert_not_called()


def test_unmount_disk_does_not_mutate_storage_config():
    services = _services()
    app = _app_with_services(services)

    with patch(
        "simple_safer_server.routes.storage.unmount_disk_partitions",
        return_value="Successfully unmounted 1 partition(s).",
    ):
        response = _admin_post(app, "/api/backup_drive/unmount", {"disk": "/dev/sdb"})

    assert response.status_code == 200
    services.config_manager.set_value.assert_not_called()


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


def test_storage_safety_checks_show_existing_folder_success():
    checks = _build_storage_safety_checks(
        {"ok": True, "error": ""},
        SimpleNamespace(mode="existing_folder"),
    )

    assert checks == [
        {
            "label": "Storage marker file",
            "state": "pass",
            "detail": "Marker matches app config.",
        },
        {"label": "Write test", "state": "pass", "detail": "Last checked just now."},
        {"label": "Folder availability", "state": "pass", "detail": "Folder is writable."},
    ]


def test_storage_safety_checks_stop_after_marker_failure():
    checks = _build_storage_safety_checks(
        {
            "ok": False,
            "error": "Storage marker is missing at /srv/storage/.simple-safer-server/storage.json.",
        },
        SimpleNamespace(mode="prepared_drive"),
    )

    assert checks[0]["label"] == "Storage marker file"
    assert checks[0]["state"] == "fail"
    assert checks[1] == {
        "label": "Write test",
        "state": "pending",
        "detail": "Not checked because the marker check failed.",
    }
    assert checks[2] == {
        "label": "Prepared drive UUID match",
        "state": "pending",
        "detail": "Not checked until earlier checks pass.",
    }


def test_storage_safety_checks_show_prepared_drive_identity_failure():
    checks = _build_storage_safety_checks(
        {
            "ok": False,
            "error": "The drive mounted at the storage location does not match the configured drive UUID.",
        },
        SimpleNamespace(mode="prepared_drive"),
    )

    assert checks[0]["state"] == "pass"
    assert checks[1]["state"] == "pass"
    assert checks[2] == {
        "label": "Prepared drive UUID match",
        "state": "fail",
        "detail": "The drive mounted at the storage location does not match the configured drive UUID.",
    }
