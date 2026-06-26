import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from flask import session

from simple_safer_server.core.builtin_modules import create_builtin_module_registry
from simple_safer_server.core.module_lifecycle import (
    apply_module,
    module_apply_resources,
    ownership_manifest_for_runtime,
)
from simple_safer_server.services import runtime


def _tool_path(name):
    if name == "update-ca-certificates":
        return "/usr/sbin/update-ca-certificates"
    return None


def _create_fake_app(temp_dir, *, skip_login=True):
    with patch.dict(
        os.environ,
        {
            "SSS_MODE": "fake",
            "SSS_SKIP_LOGIN": "true" if skip_login else "false",
            "SSS_DATA_DIR": temp_dir,
        },
        clear=False,
    ):
        runtime._runtime = None
        runtime._fake_state = None
        from simple_safer_server.app_factory import create_app

        app = create_app()
        app.config["TESTING"] = True
        return app


def _finish_fake_setup(app, server_name="family-nas"):
    with app.app_context():
        services = app.extensions["simple_safer_server"]
        services.config_manager.set_value("system", "setup_complete", "true")
        services.config_manager.set_value("system", "username", "admin")
        services.config_manager.set_value("system", "server_name", server_name)
        ok, message = services.user_manager.create_user("admin", "password", is_admin=True)
        assert ok, message
        return services


def _assert_local_fontawesome_assets(page: str):
    assert 'static/vendor/fontawesome/6.4.0/css/all.min.css' in page
    assert 'static/css/theme.css' in page
    assert 'static/css/design-tokens.css' not in page
    assert "cdnjs.cloudflare.com/ajax/libs/font-awesome" not in page
    assert "fonts.googleapis.com" not in page
    assert "fonts.gstatic.com" not in page


def test_fake_dashboard_renders_storage_action_urls():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)
            services = _finish_fake_setup(app)
            services.fake_state.set_mount(True)

            with app.test_client() as client:
                response = client.get("/dashboard")

            assert response.status_code == 200
            page = response.get_data(as_text=True)
            # The server-rendered dashboard should be useful before the
            # browser's storage polling has a chance to refresh the card.
            assert 'id="storage-meter"' in page
            assert "Backup protection" in page
            assert 'hx-get="/fragments/backup-readiness"' in page
            assert 'hx-trigger="backup-readiness-refresh from:body"' in page
            assert 'd-none" id="storage-meter"' not in page
            assert "Unavailable / Unavailable GB used" not in page
            assert 'action="/unmount"' in page
            assert 'action="/mount"' in page
            assert 'id="dashboard-copy"' in page
            assert "This unmounts the configured backup drive temporarily." in page
            assert "Drive health refreshed." in page
            assert 'id="health-refresh-button"' in page
            assert "<th>Next Run</th>" in page
            assert "Disable Schedule" not in page
            assert "Enable Schedule" not in page
            assert 'data-task-schedule-control="disable-modal"' not in page
            assert "<th>Schedule</th>" not in page
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_base_template_serves_core_ui_assets_from_local_static_assets():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)
            _finish_fake_setup(app)

            with app.test_client() as client:
                response = client.get("/dashboard")

            assert response.status_code == 200
            page = response.get_data(as_text=True)
            assert 'static/vendor/webawesome/3.9.0/components/callout/callout.js' in page
            assert 'static/vendor/htmx/2.0.10/htmx.min.js' in page
            _assert_local_fontawesome_assets(page)
            assert "ka-f.webawesome.com" not in page
            assert "unpkg.com/htmx" not in page
            assert "cdn.jsdelivr.net/npm/htmx" not in page
            assert "app-bg-orbs" not in page
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_users_page_provides_localizable_browser_copy():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)
            _finish_fake_setup(app)

            with app.test_client() as client:
                response = client.get("/users")

            assert response.status_code == 200
            page = response.get_data(as_text=True)
            assert 'id="users-copy"' in page
            assert "Failed to load users." in page
            assert "You cannot delete your own account." in page
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_setup_wizard_renders_drive_refresh_controls():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)

            with app.test_client() as client:
                response = client.get("/setup")

            assert response.status_code == 200
            page = response.get_data(as_text=True)
            _assert_local_fontawesome_assets(page)
            assert "3-2-1 backup checklist" in page
            assert 'data-backup-readiness-url="/api/setup/readiness"' in page
            assert "Review Storage setup plan" in page
            assert "Review Cloud Backup setup plan" in page
            assert "Review Alerts setup plan" in page
            assert "This preview is read-only. No changes have been made to the system." in page
            assert 'data-module-help-key="existing_folder"' in page
            assert "Use this when another tool or the operating system already manages the storage folder." in page
            assert 'data-module-help-key="rclone_config"' in page
            assert "Paste a complete rclone config. SSS stores it in its own config path." in page
            assert 'data-module-help-key="smtp_password"' in page
            assert "Use an app password when your mail provider supports one." in page
            assert 'id="setup-copy"' in page
            assert "Drive formatted successfully." in page
            assert "Error connecting to MEGA." in page
            assert "Error saving rclone config." in page
            assert "No folders or files in this directory." in page
            assert "MEGA credentials are required before creating a folder." in page
            assert "timepicker.js" not in page
            assert "Setup is still missing a few required details." in page
            # The setup wizard can be open while an operator plugs in or formats
            # a disk, so both storage selectors need a manual rescan control.
            assert 'id="refreshFormatDrivesBtn"' in page
            assert "Refresh drives" in page
            assert 'id="refreshPartitionsBtn"' in page
            assert "Refresh partitions" in page
            assert "refreshFormatDrives()" in page
            assert "refreshMountDrives()" in page
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_network_file_sharing_renders_three_service_status_labels_and_help_text():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)
            _finish_fake_setup(app)

            assert "smb_routes.network_file_sharing" in app.view_functions
            assert "network_file_sharing" not in app.view_functions

            with app.test_client() as client:
                response = client.get("/network_file_sharing")

            assert response.status_code == 200
            page = response.get_data(as_text=True)
            assert "SMB Daemon (smbd)" in page
            assert "NetBIOS Discovery (nmbd)" in page
            assert "Windows Discovery (wsdd2)" in page
            assert "serves file shares" in page
            assert "helps older Windows network browsing find this server" in page
            assert "helps modern Windows network browsing find this server" in page
            assert 'data-module-help-key="share_name"' in page
            assert "Use letters, numbers, hyphens, and underscores so Samba clients can open the share reliably." in page
            assert 'data-module-help-key="valid_users"' in page
            assert "Limit write access to the users who should be able to copy files here." in page
            assert 'id="wsdd2Status"' in page
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_smb_status_api_returns_flat_three_service_object():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)
            _finish_fake_setup(app)

            with app.test_client() as client:
                response = client.get("/api/smb/status")

            assert response.status_code == 200
            assert response.get_json()["data"] == {
                "smbd": "active",
                "nmbd": "active",
                "wsdd2": "active",
            }
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_fake_task_detail_omits_schedule_controls_and_modal():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)
            _finish_fake_setup(app)

            with app.test_client() as client:
                response = client.get("/task/Cloud%20Backup")

            assert response.status_code == 200
            page = response.get_data(as_text=True)
            assert "Disable Schedule" not in page
            assert "Enable Schedule" not in page
            assert "1 hour" not in page
            assert "6 hours" not in page
            assert "24 hours" not in page
            assert "7 days" not in page
            assert 'data-task-schedule-control="disable-modal"' not in page
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_browser_titles_use_configured_hostname_after_setup():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)
            _finish_fake_setup(app, server_name="family-nas")

            with app.test_client() as client:
                dashboard_response = client.get("/dashboard")
                task_response = client.get("/task/Cloud%20Backup")
                ddns_response = client.get("/ddns")

            assert dashboard_response.status_code == 200
            assert "<title>Overview - family-nas</title>" in dashboard_response.get_data(
                as_text=True
            )
            assert task_response.status_code == 200
            assert "<title>Cloud Backup - family-nas</title>" in task_response.get_data(
                as_text=True
            )
            assert ddns_response.status_code == 200
            assert "<title>DDNS - family-nas</title>" in ddns_response.get_data(as_text=True)
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_sidebar_nav_items_are_built_from_module_metadata():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)
            _finish_fake_setup(app)

            with app.test_request_context("/storage/change-drive"):
                session["username"] = "admin"
                context = {}
                for processor in app.template_context_processors[None]:
                    context.update(processor())

            items = context["sidebar_nav_items"]
            labels = [item["label"] for item in items]
            module_labels = [
                item.label
                for module in create_builtin_module_registry().list_modules()
                for item in module.nav_items
            ]

            assert labels == [
                "Overview",
                "File Sharing",
                "Users",
                "Storage",
                "Drive Health",
                "DDNS",
                "Cloud Backup",
                "System Updates",
                "Alerts",
            ]
            assert all(label in labels for label in module_labels)
            storage = next(item for item in items if item["label"] == "Storage")
            assert "storage_routes.storage_change_drive_page" in storage["active_endpoints"]
            assert context["_"]("Ready") == "Ready"
            assert context["gettext"]("Ready") == "Ready"
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_alerts_email_config_requires_module_apply_before_write():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)
            services = _finish_fake_setup(app)
            helper = MagicMock()
            services.alerts_service._privileged_actions = helper
            payload = {
                "email_address": "admin@example.com",
                "from_address": "server@example.com",
                "smtp_server": "smtp.example.com",
                "smtp_port": "587",
                "smtp_username": "server",
                "smtp_password": "secret",
            }

            with app.test_client() as client:
                blocked_response = client.post("/api/alerts/email-config", json=payload)
                with patch("simple_safer_server.core.module_checks.shutil.which", _tool_path):
                    apply_module(
                        create_builtin_module_registry().module_for_slug("alerts"),
                        services.runtime,
                    )
                allowed_response = client.post("/api/alerts/email-config", json=payload)

            assert blocked_response.status_code == 409
            assert blocked_response.get_json()["type"].endswith("#module-setup-required")
            assert allowed_response.status_code == 200
            helper.run.assert_called_once_with(
                "alerts.write-smtp-config",
                {
                    "from_address": "server@example.com",
                    "smtp_server": "smtp.example.com",
                    "smtp_port": "587",
                    "smtp_username": "server",
                    "smtp_password": "secret",
                },
            )
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_cloud_backup_config_requires_module_apply_before_rclone_write():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)
            services = _finish_fake_setup(app)
            payload = {
                "cloud_mode": "advanced",
                "rclone_config": "[remote]\ntype = test\n",
                "remote_name": "remote:/backups",
            }

            with app.test_client() as client:
                blocked_response = client.post("/api/cloud_backup/config", json=payload)
                with patch(
                    "simple_safer_server.core.module_checks.shutil.which",
                    return_value="/usr/bin/rclone",
                ):
                    apply_module(
                        create_builtin_module_registry().module_for_slug("cloud-backup"),
                        services.runtime,
                    )
                allowed_response = client.post("/api/cloud_backup/config", json=payload)

            assert blocked_response.status_code == 409
            assert blocked_response.get_json()["type"].endswith("#module-setup-required")
            assert allowed_response.status_code == 200
            rclone_config = services.runtime.rclone_config_dir / "rclone.conf"
            assert rclone_config.read_text(encoding="utf-8") == "[remote]\ntype = test\n"
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_login_title_uses_configured_hostname_without_auto_login():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir, skip_login=False)
            _finish_fake_setup(app, server_name="family-nas")

            with app.test_client() as client:
                response = client.get("/login")

            assert response.status_code == 200
            page = response.get_data(as_text=True)
            _assert_local_fontawesome_assets(page)
            assert "<title>Sign in - family-nas</title>" in page
            assert 'id="login-copy"' in page
            assert "Login failed" in page
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_setup_title_keeps_product_name_before_server_name_is_chosen():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)

            with app.test_client() as client:
                response = client.get("/setup")

            assert response.status_code == 200
            assert "<title>Setup — SimpleSaferServer</title>" in response.get_data(as_text=True)
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_smb_share_list_returns_validation_error_for_malformed_sss_shares_file():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)
            services = _finish_fake_setup(app)
            shares_path = Path(services.runtime.samba_dir) / "simple_safer_server_shares.conf"
            shares_path.parent.mkdir(parents=True, exist_ok=True)
            shares_path.write_text("[backup]\n   path = /media/backup\n[backup]\n")

            with app.test_client() as client:
                response = client.get("/api/smb/shares")

            payload = response.get_json()
            assert response.status_code == 400
            assert payload["detail"].startswith(
                "The SimpleSaferServer shares file is unsupported or malformed"
            )
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_smb_share_list_marks_unmanaged_verification_success_with_detected_shares():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)
            services = _finish_fake_setup(app)

            with patch.object(
                services.smb_manager,
                "list_unmanaged_shares",
                return_value=[{"name": "media"}, {"name": "photos"}],
            ):
                with app.test_client() as client:
                    response = client.get("/api/smb/shares")

            payload = response.get_json()
            assert response.status_code == 200
            assert payload["data"]["unmanaged_shares_verified"] is True
            assert payload["data"]["unmanaged_shares_detected"] is True
            assert payload["data"]["unmanaged_share_count"] == 2
            assert payload["data"]["unmanaged_share_names"] == ["media", "photos"]
            assert payload["data"]["unmanaged_share_verification_error"] is None
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_smb_share_list_marks_unmanaged_verification_success_with_no_unmanaged_shares():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)
            services = _finish_fake_setup(app)

            with patch.object(services.smb_manager, "list_unmanaged_shares", return_value=[]):
                with app.test_client() as client:
                    response = client.get("/api/smb/shares")

            payload = response.get_json()
            assert response.status_code == 200
            assert payload["data"]["unmanaged_shares_verified"] is True
            assert payload["data"]["unmanaged_shares_detected"] is False
            assert payload["data"]["unmanaged_share_count"] == 0
            assert payload["data"]["unmanaged_share_names"] == []
            assert payload["data"]["unmanaged_share_verification_error"] is None
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_smb_share_list_surfaces_unmanaged_verification_failure_without_hiding_shares():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)
            services = _finish_fake_setup(app)
            shares_path = Path(services.runtime.samba_dir) / "simple_safer_server_shares.conf"
            shares_path.parent.mkdir(parents=True, exist_ok=True)
            shares_path.write_text("[backup]\n   path = /media/backup\n")

            from simple_safer_server.modules.file_sharing import SMBConfigError

            with patch.object(
                services.smb_manager,
                "list_unmanaged_shares",
                side_effect=SMBConfigError("Could not inspect the effective Samba config: boom"),
            ):
                with app.test_client() as client:
                    response = client.get("/api/smb/shares")

            payload = response.get_json()
            assert response.status_code == 200
            assert [share["name"] for share in payload["data"]["shares"]] == ["backup"]
            assert payload["data"]["unmanaged_shares_verified"] is False
            assert payload["data"]["unmanaged_shares_detected"] is False
            assert payload["data"]["unmanaged_share_count"] is None
            assert payload["data"]["unmanaged_share_names"] == []
            assert (
                "Could not inspect the effective Samba config"
                in payload["data"]["unmanaged_share_verification_error"]
            )
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_smb_share_add_surfaces_controlled_operation_detail():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)
            services = _finish_fake_setup(app)
            file_sharing = create_builtin_module_registry().module_for_slug("file-sharing")
            ownership_manifest_for_runtime(services.runtime).record_module_resources(
                file_sharing.slug,
                module_apply_resources(file_sharing),
            )

            from simple_safer_server.modules.file_sharing import SMBOperationError

            detail = "Samba share update failed and rollback could not restart smbd."
            with patch.object(
                services.smb_manager,
                "create_managed_share",
                side_effect=SMBOperationError(detail),
            ):
                with app.test_client() as client:
                    response = client.post(
                        "/api/smb/shares",
                        json={
                            "name": "backup",
                            "path": "/media/backup",
                            "writable": True,
                            "comment": "",
                            "users": [],
                        },
                    )

            payload = response.get_json()
            assert response.status_code == 500
            assert payload["type"].endswith("#smb-operation-failed")
            assert payload["detail"] == detail
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_network_file_sharing_renders_unmanaged_verification_warning_state():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)
            _finish_fake_setup(app)

            with app.test_client() as client:
                response = client.get("/network_file_sharing")

            assert response.status_code == 200
            page = response.get_data(as_text=True)
            assert "unmanaged_shares_verified" in page
            assert "Unmanaged share verification failed" in page
            assert "Could not verify unmanaged Samba shares" in page
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state
