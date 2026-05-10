import os
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

        app, _socketio = create_app()
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
