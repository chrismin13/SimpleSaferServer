import os
from tempfile import TemporaryDirectory
from unittest.mock import patch

from simple_safer_server.services import runtime
from simple_safer_server.services.feature_flags import parse_disabled_features


def _create_fake_app(temp_dir):
    with patch.dict(
        os.environ,
        {
            "SSS_MODE": "fake",
            "SSS_SKIP_LOGIN": "true",
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


def _finish_fake_setup(app, *, disabled_features=""):
    with app.app_context():
        services = app.extensions["simple_safer_server"]
        services.config_manager.set_value("system", "setup_complete", "true")
        services.config_manager.set_value("system", "username", "admin")
        services.config_manager.set_value("system", "server_name", "family-nas")
        services.config_manager.set_value("system", "disabled_features", disabled_features)
        ok, message = services.user_manager.create_user("admin", "password", is_admin=True)
        assert ok, message
        return services


def test_disabled_feature_csv_accepts_common_spellings_and_ignores_unknown_values():
    disabled = parse_disabled_features("DDNS, network-file-sharing, unknown, app update")

    assert disabled == {"ddns", "file_sharing", "system_updates"}


def test_disabled_features_hide_nav_dashboard_tiles_and_related_tasks():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)
            _finish_fake_setup(app, disabled_features="ddns, cloud_backup, file_sharing")

            with app.test_client() as client:
                response = client.get("/dashboard")

            assert response.status_code == 200
            page = response.get_data(as_text=True)
            assert 'href="/ddns"' not in page
            assert 'href="/cloud_backup"' not in page
            assert 'href="/network_file_sharing"' not in page
            assert 'id="backup-tile"' not in page
            assert 'id="sharing-tile"' not in page
            assert 'data-task-name="Cloud Backup"' not in page
            assert 'data-task-name="DDNS Update"' not in page
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_disabled_feature_blocks_html_and_api_routes_with_admin_visible_message():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)
            _finish_fake_setup(app, disabled_features="ddns")

            with app.test_client() as client:
                html_response = client.get("/ddns")
                api_response = client.post(
                    "/api/ddns/run",
                    headers={"Accept": "application/json"},
                )

            assert html_response.status_code == 403
            assert "DDNS is disabled" in html_response.get_data(as_text=True)
            assert api_response.status_code == 403
            payload = api_response.get_json()
            assert payload["title"] == "Feature disabled"
            assert payload["type"].endswith("#feature-disabled")
            assert "not a security boundary" in payload["detail"]
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_task_schedule_api_omits_tasks_for_disabled_features():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)
            _finish_fake_setup(app, disabled_features="cloud_backup, system_updates")

            with app.test_client() as client:
                response = client.get("/api/tasks/schedule")

            assert response.status_code == 200
            task_names = [task["name"] for task in response.get_json()["data"]["tasks"]]
            assert "Cloud Backup" not in task_names
            assert "App Update" not in task_names
            assert "Check Mount" in task_names
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_index_uses_first_enabled_feature_when_overview_is_disabled():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)
            _finish_fake_setup(app, disabled_features="overview")

            with app.test_client() as client:
                response = client.get("/")

            assert response.status_code == 302
            assert response.headers["Location"].endswith("/network_file_sharing")
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state
