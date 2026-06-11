import os
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from simple_safer_server.services import runtime


@pytest.fixture
def fake_app_client():
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

                app = create_app()
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
                    yield app, client
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_server_identity_api_updates_fake_mode_config(fake_app_client):
    app, client = fake_app_client

    response = client.put(
        "/api/server_identity",
        json={"server_name": "Family-NAS"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["server_name"] == "family-nas"

    get_response = client.get("/api/server_identity")
    assert get_response.status_code == 200
    assert get_response.get_json()["data"]["server_name"] == "family-nas"

    with app.app_context():
        services = app.extensions["simple_safer_server"]
        assert services.config_manager.get_value("system", "server_name") == "family-nas"


def test_server_identity_api_rejects_invalid_name_in_fake_mode(fake_app_client):
    _app, client = fake_app_client

    response = client.put(
        "/api/server_identity",
        json={"server_name": "bad name"},
    )

    assert response.status_code == 400
    assert response.get_json()["detail"].startswith("Server name may only contain")


def test_server_identity_api_rejects_missing_name_in_fake_mode(fake_app_client):
    _app, client = fake_app_client

    response = client.put("/api/server_identity", json={})

    assert response.status_code == 400
    assert (
        response.get_json()["detail"]
        == "Server name may only contain letters, numbers, and hyphens, and cannot start or end with a hyphen."
    )


def test_server_identity_api_rejects_non_object_json_in_fake_mode(fake_app_client):
    _app, client = fake_app_client

    response = client.put("/api/server_identity", json=["bad"])

    assert response.status_code == 400
    assert response.get_json()["detail"] == "Request body must be a JSON object."
