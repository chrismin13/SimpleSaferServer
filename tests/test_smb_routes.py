import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

from simple_safer_server.core.module_lifecycle import (
    module_apply_resources,
    ownership_manifest_for_runtime,
)
from simple_safer_server.modules.file_sharing.module import (
    create_module as create_file_sharing_module,
)
from simple_safer_server.modules.file_sharing.routes import smb


def _app():
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / "templates"))
    app.secret_key = "test-secret"
    app.config["TESTING"] = True
    app.extensions["simple_safer_server"] = SimpleNamespace()
    app.context_processor(
        lambda: {
            "browser_title": lambda page_name: page_name,
            "runtime_mode": "fake",
            "sidebar_nav_items": [],
            "default_mount_point": "/media/backup",
            "is_admin": True,
        }
    )
    app.register_blueprint(smb)
    app.add_url_rule("/login", "login", lambda: "login")
    app.add_url_rule("/logout", "logout", lambda: "logout")
    return app


def _record_file_sharing_setup(runtime):
    module = create_file_sharing_module()
    ownership_manifest_for_runtime(runtime).record_module_resources(
        module.slug,
        module_apply_resources(module),
    )


def _admin_get(app, path):
    client = app.test_client()
    with client.session_transaction() as session:
        session["username"] = "admin"
    with patch(
        "simple_safer_server.services.user_manager.UserManager",
        return_value=SimpleNamespace(is_admin=lambda username: username == "admin"),
    ):
        return client.get(path)


def _admin_post(app, path, json=None):
    client = app.test_client()
    with client.session_transaction() as session:
        session["username"] = "admin"
    with patch(
        "simple_safer_server.services.user_manager.UserManager",
        return_value=SimpleNamespace(is_admin=lambda username: username == "admin"),
    ):
        return client.post(path, json=json)


def test_list_dirs_keeps_dirs_field_and_adds_file_entries(tmp_path):
    app = _app()
    (tmp_path / "share").mkdir()
    (tmp_path / "readme.txt").write_text("hello", encoding="utf-8")

    response = _admin_get(app, f"/api/list_dirs?path={tmp_path}")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["dirs"] == ["share"]
    assert payload["files"] == ["readme.txt"]
    assert payload["entries"] == [
        {"name": "share", "type": "folder"},
        {"name": "readme.txt", "type": "file"},
    ]


def test_list_dirs_accepts_picker_post_shape(tmp_path):
    app = _app()
    (tmp_path / "share").mkdir()

    response = _admin_post(app, "/api/list_dirs", {"path": str(tmp_path)})

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["path"] == str(tmp_path)
    assert payload["dirs"] == ["share"]


def test_file_sharing_page_renders_module_owned_help(tmp_path):
    app = _app()
    app.extensions["simple_safer_server"].runtime = SimpleNamespace(
        data_dir=tmp_path,
        default_mount_point="/media/backup",
    )
    app.extensions["simple_safer_server"].config_manager = SimpleNamespace(
        get_value=lambda section, key, fallback="": fallback
    )

    response = _admin_get(app, "/network_file_sharing")

    assert response.status_code == 200
    assert b"<wa-callout" in response.data
    assert b"module-help-band" in response.data
    assert b"File Sharing exposes selected backup folders on the local network" in response.data
    assert b"Enable Samba management only after showing exactly which SSS-owned files" in response.data
    assert b"Restarting Samba can disconnect active file copies" in response.data
    assert b'id="file-sharing-copy"' in response.data
    assert b"/static/js/mega_folder_picker.js" in response.data
    assert b"Could not load directories." in response.data


def test_file_sharing_page_passes_browser_copy_as_json(tmp_path):
    app = _app()
    app.extensions["simple_safer_server"].runtime = SimpleNamespace(
        data_dir=tmp_path,
        default_mount_point="/media/backup",
    )
    app.extensions["simple_safer_server"].config_manager = SimpleNamespace(
        get_value=lambda section, key, fallback="": fallback
    )

    response = _admin_get(app, "/network_file_sharing")

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    match = re.search(
        r'<script type="application/json" id="file-sharing-copy">(.*?)</script>',
        page,
        re.DOTALL,
    )
    assert match is not None
    copy = json.loads(match.group(1))
    assert copy["serverIdentity"]["confirmMessage"].startswith("Change the server name")
    assert copy["unmanagedShares"]["noneDetected"] == "No unmanaged shares detected."
    assert copy["shares"]["pathMustStartWithSlash"] == "Path must start with /"
    assert copy["status"]["downMessage"] == "File sharing is not running"
    assert copy["actions"]["restartConfirmLabel"] == "Restart"


def test_restart_smb_requires_file_sharing_setup(tmp_path):
    app = _app()
    app.extensions["simple_safer_server"].runtime = SimpleNamespace(data_dir=tmp_path)
    app.extensions["simple_safer_server"].privileged_actions = SimpleNamespace(run=MagicMock())

    response = _admin_post(app, "/api/smb/restart", {})

    assert response.status_code == 409
    assert response.get_json()["type"].endswith("#module-setup-required")
    app.extensions["simple_safer_server"].privileged_actions.run.assert_not_called()


def test_restart_smb_uses_privileged_action(tmp_path):
    app = _app()
    runtime = SimpleNamespace(data_dir=tmp_path)
    app.extensions["simple_safer_server"].runtime = runtime
    _record_file_sharing_setup(runtime)
    app.extensions["simple_safer_server"].privileged_actions = SimpleNamespace(
        run=MagicMock(
            return_value=SimpleNamespace(data={"message": "File sharing services reloaded."})
        )
    )

    response = _admin_post(app, "/api/smb/restart", {})

    assert response.status_code == 200
    assert response.get_json()["message"] == "File sharing services reloaded."
    app.extensions["simple_safer_server"].privileged_actions.run.assert_called_once_with(
        "file-sharing.reload",
        {},
    )
