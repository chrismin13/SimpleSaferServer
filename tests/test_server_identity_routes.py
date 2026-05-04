import os
from tempfile import TemporaryDirectory
from unittest.mock import patch

from simple_safer_server.services import runtime


def test_server_identity_api_updates_fake_mode_config():
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

                with app.test_client() as client:
                    response = client.put(
                        "/api/server_identity",
                        json={"server_name": "Family-NAS"},
                    )

                assert response.status_code == 200
                payload = response.get_json()
                assert payload["data"]["server_name"] == "family-nas"

                with app.app_context():
                    services = app.extensions["simple_safer_server"]
                    assert (
                        services.config_manager.get_value("system", "server_name") == "family-nas"
                    )
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_server_identity_api_rejects_invalid_name_in_fake_mode():
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

                with app.test_client() as client:
                    response = client.put(
                        "/api/server_identity",
                        json={"server_name": "bad name"},
                    )

                assert response.status_code == 400
                assert response.get_json()["detail"].startswith("Server name may only contain")
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state
