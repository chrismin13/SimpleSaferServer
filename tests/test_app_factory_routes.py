import os
from tempfile import TemporaryDirectory
from unittest.mock import patch

from simple_safer_server.services import runtime


def test_fake_dashboard_renders_storage_action_urls():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
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

                app, _socketio = create_app()
                app.config["TESTING"] = True

                with app.app_context():
                    services = app.extensions["simple_safer_server"]
                    services.config_manager.set_value("system", "setup_complete", "true")
                    services.config_manager.set_value("system", "username", "admin")
                    ok, message = services.user_manager.create_user(
                        "admin", "password", is_admin=True
                    )
                    assert ok, message
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
