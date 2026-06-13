import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from simple_safer_server.services import runtime


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
            assert 'd-none" id="storage-meter"' not in page
            assert "Unavailable / Unavailable GB used" not in page
            assert 'action="/unmount"' in page
            assert 'action="/mount"' in page
            assert 'id="health-refresh-button"' in page
            assert "<th>Next Run</th>" in page
            assert "Disable Schedule" in page
            assert "Enable Schedule" in page
            assert 'data-task-schedule-control="disable-modal"' in page
            assert "<th>Schedule</th>" not in page
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


def test_dashboard_file_sharing_summary_tracks_wsdd2_and_three_state_rules():
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
            # Operational requires smbd active and discovery services active-or-unavailable
            assert "discoveryOk(data.nmbd)" in page
            assert "discoveryOk(data.wsdd2)" in page
            assert "data.smbd === 'active'" in page
            assert "wsdd2: ${data.wsdd2}" in page
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_fake_task_detail_renders_schedule_controls_and_modal():
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
            assert "Disable Schedule" in page
            assert "Enable Schedule" in page
            assert "1 hour" in page
            assert "6 hours" in page
            assert "24 hours" in page
            assert "7 days" in page
            assert "Permanent" in page
            assert "Manual Start still works" in page
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
                task_response = client.get("/task/App%20Update")
                ddns_response = client.get("/ddns")

            assert dashboard_response.status_code == 200
            assert "<title>Overview - family-nas</title>" in dashboard_response.get_data(
                as_text=True
            )
            assert task_response.status_code == 200
            assert "<title>App Update - family-nas</title>" in task_response.get_data(as_text=True)
            assert ddns_response.status_code == 200
            assert "<title>DDNS - family-nas</title>" in ddns_response.get_data(as_text=True)
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
            assert "<title>Sign in - family-nas</title>" in response.get_data(as_text=True)
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
                return_value=[{"name": "media"}, {"name": "legacy"}],
            ):
                with app.test_client() as client:
                    response = client.get("/api/smb/shares")

            payload = response.get_json()
            assert response.status_code == 200
            assert payload["data"]["unmanaged_shares_verified"] is True
            assert payload["data"]["unmanaged_shares_detected"] is True
            assert payload["data"]["unmanaged_share_count"] == 2
            assert payload["data"]["unmanaged_share_names"] == ["media", "legacy"]
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

            from simple_safer_server.services.smb_manager import SMBConfigError

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

            from simple_safer_server.services.smb_manager import SMBOperationError

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


def test_discovery_badges_use_three_tier_and_smbd_stays_binary():
    """Discovery services (nmbd, wsdd2) use three-tier badge colors:
    active → badge-success, inactive → badge-warning, unavailable → badge-neutral.
    smbd stays binary: active → badge-success, anything else → badge-danger.
    """
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

            # smbd stays binary: active → success, anything else → danger
            assert "data.smbd === 'active' ? 'badge badge-success' : 'badge badge-danger'" in page

            # nmbd and wsdd2 must NOT use the binary danger pattern
            assert (
                "data.nmbd === 'active' ? 'badge badge-success' : 'badge badge-danger'" not in page
            )
            assert (
                "data.wsdd2 === 'active' ? 'badge badge-success' : 'badge badge-danger'" not in page
            )

            # discoveryBadgeClass helper maps the three tiers:
            # active → badge-success, inactive → badge-warning, other → badge-neutral
            assert "discoveryBadgeClass(data.nmbd)" in page
            assert "discoveryBadgeClass(data.wsdd2)" in page
            assert "status === 'active') return 'badge-success'" in page
            assert "status === 'inactive') return 'badge-warning'" in page
            assert "return 'badge-neutral'" in page

            # Overall status treats 'unavailable' as non-degrading
            assert "discoveryOk(data.nmbd)" in page
            assert "discoveryOk(data.wsdd2)" in page
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state
