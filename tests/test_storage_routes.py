from pathlib import Path
from tempfile import mkdtemp
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest
from flask import Flask

from simple_safer_server.core.module_lifecycle import (
    module_apply_resources,
    ownership_manifest_for_runtime,
)
from simple_safer_server.modules.storage.module import create_module as create_storage_module
from simple_safer_server.modules.storage.routes import _build_storage_safety_checks, storage


def _apply_storage_module(services):
    module = create_storage_module()
    ownership_manifest_for_runtime(services.runtime).record_module_resources(
        module.slug,
        module_apply_resources(module),
    )


def _app_with_services(services, *, storage_applied=True):
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.secret_key = "test-secret"
    app.config["TESTING"] = True
    app.extensions["simple_safer_server"] = services
    if storage_applied:
        _apply_storage_module(services)
    app.jinja_env.globals["browser_title"] = lambda title: title
    app.register_blueprint(storage)
    app.add_url_rule("/login", "login", lambda: "login")
    app.add_url_rule("/", "task_routes.dashboard", lambda: "dashboard")
    app.add_url_rule("/shares", "smb_routes.network_file_sharing", lambda: "shares")
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
    system_utils.validate_worker_task_config.return_value = (True, None)
    system_updates_manager = MagicMock()
    system_updates_manager.get_lock_status.return_value = {"locked": False}
    return SimpleNamespace(
        config_manager=config_manager,
        system_utils=system_utils,
        system_updates_manager=system_updates_manager,
        smb_manager=MagicMock(),
        privileged_actions=MagicMock(),
        runtime=SimpleNamespace(
            is_fake=True,
            default_mount_point="/media/backup",
            data_dir=Path(mkdtemp(prefix="sss-storage-test-")),
        ),
        command_runner=MagicMock(),
        storage_service=MagicMock(),
        task_service=SimpleNamespace(get_check_mount_next_run=lambda: None),
    )


def _prepared_location(path="/srv/storage"):
    return SimpleNamespace(
        path=path,
        mode="existing_folder",
        storage_id="new-storage-id",
        mount_source="",
        mount_target="",
        mount_fstype="",
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
    assert "Change Managed Drive" in body
    assert "Format a drive" in body
    assert "Use an NTFS partition" in body
    assert 'data-module-help-key="mount_point"' in body
    assert "Where SSS mounts the managed backup partition." in body
    assert 'data-module-help-key="ntfs_driver"' in body
    assert "Use ntfs-3g unless this host is known to work better with the kernel ntfs3 driver." in body
    assert 'id="storage-change-drive-copy"' in body
    assert "Failed to format the selected disk." in body
    assert "SimpleSaferServer storage will not change" in body
    assert "/static/js/storage_change_drive.js" in body


def test_storage_write_route_requires_module_apply():
    services = _services()
    app = _app_with_services(services, storage_applied=False)

    response = _admin_post(app, "/mount", {})

    assert response.status_code == 409
    assert response.get_json()["type"].endswith("#module-setup-required")


def test_existing_folder_page_requires_admin_session():
    app = _app_with_services(_services())

    response = app.test_client().get("/storage/existing-folder")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_existing_folder_page_renders_inside_storage_shell():
    app = _app_with_services(_services())

    with patch(
        "simple_safer_server.modules.storage.routes.get_storage_location",
        return_value=SimpleNamespace(mode="existing_folder", path="/srv/storage"),
    ):
        response = _admin_get(app, "/storage/existing-folder")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Use an existing folder" in body
    assert "Existing Folder Path" in body
    assert 'data-module-help-key="existing_folder"' in body
    assert "Use this when another tool or the operating system already manages the storage folder." in body
    assert "Use This Folder" in body
    assert "browseExistingStorageBtn" in body
    assert "existingStorageFolderPickerModal" in body
    assert 'id="storage-existing-folder-copy"' in body
    assert "Could not save storage folder." in body
    assert "No folders or files in this directory." in body
    assert "/static/js/mega_folder_picker.js" in body
    assert "/static/js/storage_existing_folder.js" in body


def test_storage_page_links_to_configuration_change_pages_without_scan_action():
    services = _services()
    app = _app_with_services(services)

    with (
        patch(
            "simple_safer_server.modules.storage.routes.get_storage_location",
            return_value=SimpleNamespace(
                mode="managed_drive",
                path="/media/backup",
                app_manages_mount=True,
            ),
        ),
        patch(
            "simple_safer_server.modules.storage.routes.passive_storage_status",
            return_value={"checked": False, "ok": True, "error": ""},
        ),
        patch(
            "simple_safer_server.modules.storage.routes.get_managed_ntfs_driver",
            return_value="ntfs-3g",
        ),
    ):
        response = _admin_get(app, "/storage")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "<wa-callout" in body
    assert "module-help-band" in body
    assert "Storage is where backup data lands before any cloud copy runs" in body
    assert "Use an existing folder by default" in body
    assert "Formatting or remounting drives can destroy data" in body
    assert "Change managed drive" in body
    assert "/storage/change-drive" in body
    assert "Use an existing folder" in body
    assert "Choose folder" in body
    assert "/storage/existing-folder" in body
    assert "Scan Connected Drives" not in body
    assert "Run safety check" in body
    assert 'id="storage-copy"' in body
    assert "Could not run storage safety check." in body
    assert "Repair Storage Marker" in body


def test_storage_page_does_not_run_active_storage_status():
    services = _services()
    app = _app_with_services(services)

    with (
        patch(
            "simple_safer_server.modules.storage.routes.get_storage_location",
            return_value=SimpleNamespace(
                mode="managed_drive",
                path="/media/backup",
                app_manages_mount=True,
            ),
        ),
        patch(
            "simple_safer_server.modules.storage.routes.passive_storage_status",
            return_value={"checked": False, "ok": True, "error": ""},
        ) as passive_status,
        patch("simple_safer_server.modules.storage.routes.storage_status") as active_status,
        patch(
            "simple_safer_server.modules.storage.routes.get_managed_ntfs_driver",
            return_value="ntfs-3g",
        ),
    ):
        response = _admin_get(app, "/storage")

    assert response.status_code == 200
    passive_status.assert_called_once()
    active_status.assert_not_called()


def test_dashboard_unmount_uses_privileged_managed_unmount_action():
    services = _services()
    services.runtime.is_fake = False
    services.privileged_actions.run.return_value = SimpleNamespace(data={})
    app = _app_with_services(services)

    with patch(
        "simple_safer_server.modules.storage.routes.get_storage_location",
        return_value=SimpleNamespace(mode="managed_drive", path="/media/backup"),
    ):
        response = _admin_post(app, "/unmount", {})

    assert response.status_code == 200
    assert "Drive unmounted and powered down" in response.get_json()["message"]
    services.privileged_actions.run.assert_called_once_with(
        "storage.managed-unmount", {"power_down": True}
    )


def test_restart_uses_privileged_reboot_action():
    services = _services()
    services.system_updates_manager.get_lock_status.return_value = {"locked": False}
    services.privileged_actions.run.return_value = SimpleNamespace(
        data={"message": "System is restarting..."}
    )
    app = _app_with_services(services)

    response = _admin_post(app, "/restart", {})

    assert response.status_code == 200
    assert response.get_json()["message"] == "System is restarting..."
    services.privileged_actions.run.assert_called_once_with("system.reboot", {})
    services.storage_service.restart_system.assert_not_called()


def test_restart_requires_storage_module_apply():
    services = _services()
    app = _app_with_services(services, storage_applied=False)

    response = _admin_post(app, "/restart", {})

    assert response.status_code == 409
    assert response.get_json()["type"].endswith("#module-setup-required")
    services.privileged_actions.run.assert_not_called()


def test_mount_uses_privileged_mount_action_in_real_mode():
    services = _services()
    services.runtime.is_fake = False
    services.privileged_actions.run.return_value = SimpleNamespace(
        data={"message": "Drive mounted and available for use."}
    )
    app = _app_with_services(services)

    response = _admin_post(app, "/mount", {})

    assert response.status_code == 200
    assert response.get_json()["message"] == "Drive mounted and available for use."
    services.privileged_actions.run.assert_called_once_with("storage.mount", {})
    services.storage_service.mount_dashboard_drive.assert_not_called()


def test_mount_uses_local_storage_service_in_fake_mode():
    services = _services()
    services.storage_service.mount_dashboard_drive.return_value = "Fake mount complete."
    app = _app_with_services(services)

    response = _admin_post(app, "/mount", {})

    assert response.status_code == 200
    assert response.get_json()["message"] == "Fake mount complete."
    services.storage_service.mount_dashboard_drive.assert_called_once_with()
    services.privileged_actions.run.assert_not_called()


def test_shutdown_uses_privileged_poweroff_action():
    services = _services()
    services.system_updates_manager.get_lock_status.return_value = {"locked": False}
    services.privileged_actions.run.return_value = SimpleNamespace(
        data={"message": "System is shutting down..."}
    )
    app = _app_with_services(services)

    response = _admin_post(app, "/shutdown", {})

    assert response.status_code == 200
    assert response.get_json()["message"] == "System is shutting down..."
    services.privileged_actions.run.assert_called_once_with("system.poweroff", {})
    services.storage_service.shutdown_system.assert_not_called()


def test_shutdown_requires_storage_module_apply():
    services = _services()
    app = _app_with_services(services, storage_applied=False)

    response = _admin_post(app, "/shutdown", {})

    assert response.status_code == 409
    assert response.get_json()["type"].endswith("#module-setup-required")
    services.privileged_actions.run.assert_not_called()


def test_manual_storage_safety_check_runs_active_storage_status():
    services = _services()
    app = _app_with_services(services)

    with patch(
        "simple_safer_server.modules.storage.routes.storage_status",
        return_value={
            "checked": True,
            "ok": True,
            "error": "",
            "location": SimpleNamespace(mode="existing_folder"),
        },
    ) as active_status:
        response = _admin_post(app, "/api/storage/safety-check", {})

    assert response.status_code == 200
    active_status.assert_called_once()
    payload = response.get_json()
    assert payload["data"]["ok"] is True
    assert payload["data"]["safety_checks"][1]["label"] == "Write test"


def test_storage_status_api_uses_passive_status():
    services = _services()
    app = _app_with_services(services)

    with (
        patch(
            "simple_safer_server.modules.storage.routes.passive_storage_status",
            return_value={"checked": False, "ok": True, "error": ""},
        ) as passive_status,
        patch("simple_safer_server.modules.storage.routes.storage_status") as active_status,
        patch(
            "simple_safer_server.modules.storage.routes.psutil.disk_usage",
            return_value=SimpleNamespace(
                used=10 * 1024**3,
                total=100 * 1024**3,
                percent=10.0,
            ),
        ),
    ):
        response = _admin_get(app, "/api/storage/status")

    assert response.status_code == 200
    passive_status.assert_called_once()
    active_status.assert_not_called()
    assert response.get_json()["data"]["storage_usage"] == "10.0%"


def test_storage_status_api_marks_existing_folder_unavailable_when_disk_usage_fails():
    services = _services()
    app = _app_with_services(services)

    with patch(
        "simple_safer_server.modules.storage.routes.psutil.disk_usage",
        side_effect=OSError,
    ):
        response = _admin_get(app, "/api/storage/status")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["available"] is False
    assert payload["disk_available"] is False
    assert payload["error"] == "Storage path is not readable."


def test_storage_status_api_does_not_hide_unexpected_disk_usage_errors():
    services = _services()
    app = _app_with_services(services)

    with (
        patch(
            "simple_safer_server.modules.storage.routes.psutil.disk_usage",
            side_effect=RuntimeError("unexpected"),
        ),
        pytest.raises(RuntimeError, match="unexpected"),
    ):
        _admin_get(app, "/api/storage/status")


def test_existing_folder_storage_refreshes_worker_task_config(tmp_path):
    services = _services()
    services.runtime.data_dir = tmp_path
    app = _app_with_services(services)

    with patch(
        "simple_safer_server.modules.storage.routes.prepare_existing_folder",
        return_value=_prepared_location(),
    ):
        response = _admin_post(app, "/api/storage/existing-folder", {"path": "/srv/storage"})

    assert response.status_code == 200
    services.system_utils.validate_worker_task_config.assert_called_once_with(
        services.config_manager.get_all_config.return_value
    )
    records = ownership_manifest_for_runtime(services.runtime).list_records()
    assert {record.module_slug for record in records} == {"file-sharing", "storage"}
    assert any(
        record.module_slug == "storage"
        and record.kind == "marker-file"
        and record.identifier == "/srv/storage/.simple-safer-server/storage.json"
        for record in records
    )
    assert not any(record.kind == "fstab-entry" for record in records)


def test_storage_list_path_returns_folders_and_files(tmp_path):
    services = _services()
    app = _app_with_services(services)
    (tmp_path / "photos").mkdir()
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")

    response = _admin_post(app, "/api/storage/list-path", {"path": str(tmp_path)})

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["path"] == str(tmp_path)
    assert payload["dirs"] == ["photos"]
    assert payload["files"] == ["notes.txt"]
    assert payload["entries"] == [
        {"name": "photos", "type": "folder"},
        {"name": "notes.txt", "type": "file"},
    ]


def test_managed_drive_storage_uses_privileged_action():
    services = _services()
    services.config_manager.get_all_config.return_value["storage"]["mode"] = "managed_drive"
    services.privileged_actions.run.return_value = SimpleNamespace(
        data={"mount_point": "/media/backup"}
    )
    app = _app_with_services(services)

    response = _admin_post(
        app,
        "/api/backup_drive/configure",
        {"partition": "/dev/sdb1", "mount_point": "/media/backup"},
    )

    assert response.status_code == 200
    services.privileged_actions.run.assert_called_once_with(
        "storage.managed-drive",
        {
            "partition": "/dev/sdb1",
            "mount_point": "/media/backup",
            "ntfs_driver": "ntfs-3g",
        },
    )


def test_managed_drive_configure_passes_ntfs_driver():
    services = _services()
    services.privileged_actions.run.return_value = SimpleNamespace(
        data={"mount_point": "/media/backup", "ntfs_driver": "ntfs3"}
    )
    app = _app_with_services(services)

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
    assert services.privileged_actions.run.call_args.args[1]["ntfs_driver"] == "ntfs3"


def test_format_drive_list_uses_broad_scan():
    services = _services()
    app = _app_with_services(services)

    with patch(
        "simple_safer_server.modules.storage.routes.list_available_drives",
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
    services.privileged_actions.run.side_effect = Exception("boom")
    app = _app_with_services(services)

    response = _admin_post(app, "/api/backup_drive/format", {"disk": "/dev/sdb"})

    assert response.status_code == 500
    assert "Could not format" in response.get_json()["detail"]


def test_format_drive_does_not_mutate_storage_config():
    services = _services()
    services.privileged_actions.run.return_value = SimpleNamespace(
        data={
            "disk": "/dev/sdb",
            "partition": "/dev/sdb1",
            "message": "Successfully formatted /dev/sdb1 as NTFS.",
        }
    )
    app = _app_with_services(services)

    response = _admin_post(app, "/api/backup_drive/format", {"disk": "/dev/sdb"})

    assert response.status_code == 200
    services.privileged_actions.run.assert_called_once_with("storage.format", {"disk": "/dev/sdb"})
    services.config_manager.set_value.assert_not_called()


def test_unmount_disk_does_not_mutate_storage_config():
    services = _services()
    services.privileged_actions.run.return_value = SimpleNamespace(
        data={"message": "Successfully unmounted 1 partition(s)."}
    )
    app = _app_with_services(services)

    response = _admin_post(app, "/api/backup_drive/unmount", {"disk": "/dev/sdb"})

    assert response.status_code == 200
    services.privileged_actions.run.assert_called_once_with(
        "storage.unmount",
        {"disk": "/dev/sdb", "partition": "", "force_managed": False},
    )
    services.config_manager.set_value.assert_not_called()


def test_existing_folder_reports_worker_schedule_validation_failure(tmp_path):
    services = _services()
    services.runtime.data_dir = tmp_path
    services.config_manager.get_all_config.return_value = {
        "backup": {"cloud_enabled": "false", "mount_point": "/old/storage"},
        "storage": {
            "mode": "managed_drive",
            "path": "/old/storage",
            "storage_id": "old-storage-id",
            "mount_source": "",
            "mount_target": "",
            "mount_fstype": "",
        },
        "schedule": {"backup_cloud_time": "03:00"},
    }
    services.system_utils.validate_worker_task_config.return_value = (
        False,
        "worker validation failed",
    )
    app = _app_with_services(services)

    with patch(
        "simple_safer_server.modules.storage.routes.prepare_existing_folder",
        return_value=_prepared_location("/new/storage"),
    ):
        response = _admin_post(app, "/api/storage/existing-folder", {"path": "/new/storage"})

    assert response.status_code == 500
    assert "worker schedule config was not valid" in response.get_json()["detail"]
    assert "Previous storage settings were restored" in response.get_json()["detail"]
    services.smb_manager.ensure_default_backup_share.assert_has_calls(
        [
            call("/new/storage", "admin"),
            call("/old/storage", "admin"),
        ]
    )
    config_writes = services.config_manager.set_value.call_args_list
    assert config_writes.index(call("storage", "path", "/new/storage")) < config_writes.index(
        call("storage", "path", "/old/storage")
    )
    assert config_writes.index(call("backup", "mount_point", "/new/storage")) < config_writes.index(
        call("backup", "mount_point", "/old/storage")
    )


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
        {"label": "Folder is writable", "state": "pass", "detail": "Folder is writable."},
        {
            "label": "Test file cycle",
            "state": "pass",
            "detail": "Write, read, and delete succeeded.",
        },
    ]


def test_storage_safety_checks_stop_after_marker_failure():
    checks = _build_storage_safety_checks(
        {
            "ok": False,
            "error": (
                "Storage marker is missing at /srv/storage/.simple-safer-server/storage.json. "
                "If this is the correct storage folder, repair the marker."
            ),
        },
        SimpleNamespace(mode="managed_drive"),
    )

    assert checks[0]["label"] == "Storage marker file"
    assert checks[0]["state"] == "fail"
    assert checks[1] == {
        "label": "Write test",
        "state": "pending",
        "detail": "Not checked because the marker check failed.",
    }
    assert checks[2] == {
        "label": "Managed drive UUID match",
        "state": "pending",
        "detail": "Not checked until earlier checks pass.",
    }


def test_storage_safety_checks_show_managed_drive_identity_failure():
    checks = _build_storage_safety_checks(
        {
            "ok": False,
            "error": "The drive mounted at the storage location does not match the configured drive UUID.",
        },
        SimpleNamespace(mode="managed_drive"),
    )

    assert checks[0]["state"] == "pass"
    assert checks[1]["state"] == "pass"
    assert checks[2] == {
        "label": "Managed drive UUID match",
        "state": "fail",
        "detail": "The drive mounted at the storage location does not match the configured drive UUID.",
    }
