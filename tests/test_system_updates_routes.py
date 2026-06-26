from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

from simple_safer_server.modules.system_updates.routes import system_updates
from simple_safer_server.modules.system_updates.service import APP_UPDATE_UNAVAILABLE_MESSAGE


def _build_app(manager):
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / "templates"))
    app.config["TESTING"] = True
    app.secret_key = "test-secret"
    app.extensions["simple_safer_server"] = SimpleNamespace(
        system_updates_manager=manager,
        task_service=MagicMock(),
    )
    app.context_processor(lambda: {"browser_title": lambda page_name: page_name})
    app.add_url_rule("/logout", "logout", lambda: "logout")
    app.register_blueprint(system_updates)
    return app


@contextmanager
def _admin_client(app):
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True
    with (
        patch("simple_safer_server.services.user_manager.UserManager", return_value=user_manager),
        app.test_client() as client,
    ):
        yield client


def test_livepatch_setup_is_read_only():
    manager = MagicMock()
    app = _build_app(manager)

    with _admin_client(app) as client:
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.post("/api/system_updates/livepatch/setup", json={"token": ""})

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["type"].endswith("#system-updates-read-only")
    assert payload["detail"].startswith("Operating system update actions are read-only")
    manager.setup_livepatch.assert_not_called()


def test_apt_start_is_read_only():
    manager = MagicMock()
    app = _build_app(manager)

    with _admin_client(app) as client:
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.post("/api/system_updates/update/start")

    assert response.status_code == 409
    assert response.get_json()["type"].endswith("#system-updates-read-only")
    manager.start_operation.assert_not_called()


def test_apt_stop_is_read_only():
    manager = MagicMock()
    app = _build_app(manager)

    with _admin_client(app) as client:
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.post("/api/system_updates/stop")

    assert response.status_code == 409
    assert response.get_json()["type"].endswith("#system-updates-read-only")
    manager.stop_operation.assert_not_called()


def test_remove_stale_locks_is_read_only():
    manager = MagicMock()
    app = _build_app(manager)

    with _admin_client(app) as client:
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.post("/api/system_updates/remove_stale_locks")

    assert response.status_code == 409
    assert response.get_json()["type"].endswith("#system-updates-read-only")
    manager.remove_stale_locks.assert_not_called()


def test_automatic_apt_settings_post_is_read_only():
    manager = MagicMock()
    app = _build_app(manager)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with (
        patch("simple_safer_server.services.user_manager.UserManager", return_value=user_manager),
        app.test_client() as client,
    ):
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.post("/api/system_updates/settings", json={"update_package_lists": True})

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["detail"].startswith("Automatic apt settings are read-only")
    manager.save_settings.assert_not_called()


def test_system_updates_page_shows_read_only_settings_without_form_controls():
    manager = MagicMock()
    app = _build_app(manager)

    with _admin_client(app) as client:
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.get("/system_updates")

    assert response.status_code == 200
    assert b"auto-updates-form" not in response.data
    assert b"auto-unattended-upgrade" not in response.data
    assert b"auto-upgrades-status" in response.data
    assert b"<wa-callout" in response.data
    assert b"module-help-band" in response.data
    assert b"System Updates shows OS update state without owning OS update policy" in response.data
    assert b"Keep this module read-only unless OS update ownership becomes explicit" in response.data
    assert b'id="system-updates-copy"' in response.data
    assert b"Application update status refreshed." in response.data
    assert b"Could not load system updates." in response.data
    assert b"SSS does not install, enable, or configure automatic OS updates." in response.data
    assert b"automatic upgrades will need that package" not in response.data


def test_application_update_returns_conflict_when_no_update_is_available():
    manager = MagicMock()
    manager.get_application_update_status.return_value = {
        "can_update": False,
        "message": "Up to date with origin/main.",
    }
    app = _build_app(manager)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with (
        patch("simple_safer_server.services.user_manager.UserManager", return_value=user_manager),
        app.test_client() as client,
    ):
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.post("/api/system_updates/application/update")

    assert response.status_code == 409
    assert response.get_json()["detail"] == "Up to date with origin/main."


def test_application_update_does_not_start_worker_until_release_updater_exists():
    manager = MagicMock()
    manager.get_application_update_status.return_value = {
        "can_update": True,
        "message": APP_UPDATE_UNAVAILABLE_MESSAGE,
    }
    app = _build_app(manager)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with (
        patch("simple_safer_server.services.user_manager.UserManager", return_value=user_manager),
        app.test_client() as client,
    ):
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.post("/api/system_updates/application/update")

    assert response.status_code == 409
    assert response.get_json()["detail"].startswith("Application self-updates are unavailable")
    app.extensions["simple_safer_server"].task_service.get_task.assert_not_called()
