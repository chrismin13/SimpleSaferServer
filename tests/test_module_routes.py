import os
from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from simple_safer_server.cli import run as run_cli
from simple_safer_server.core.builtin_modules import create_builtin_module_registry
from simple_safer_server.core.module_lifecycle import (
    module_apply_resources,
    ownership_manifest_for_runtime,
)
from simple_safer_server.core.module_serialization import module_plan_data
from simple_safer_server.services import runtime


def _tool_path(name: str) -> str | None:
    if name == "update-ca-certificates":
        return "/usr/sbin/update-ca-certificates"
    return None


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
        with app.app_context():
            services = app.extensions["simple_safer_server"]
            services.config_manager.set_value("system", "setup_complete", "true")
            services.config_manager.set_value("system", "username", "admin")
            ok, message = services.user_manager.create_user("admin", "password", is_admin=True)
            assert ok, message
        return app


def _admin_client(app):
    user_manager = app.extensions["simple_safer_server"].user_manager
    return patch(
        "simple_safer_server.services.user_manager.UserManager",
        return_value=user_manager,
    )


def _run_cli(args):
    stdout = StringIO()
    stderr = StringIO()
    exit_code = run_cli(args, stdout=stdout, stderr=stderr)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def test_module_plan_api_uses_shared_plan_shape():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)
            expected_plan = module_plan_data(
                create_builtin_module_registry()
                .module_for_slug("cloud-backup")
                .build_plan()
            )

            with _admin_client(app), app.test_client() as client:
                with client.session_transaction() as session:
                    session["username"] = "admin"
                response = client.get("/api/modules/cloud-backup/plan")

        assert response.status_code == 200
        payload = response.get_json()["data"]
        assert payload["module"]["slug"] == "cloud-backup"
        assert payload["module"]["help"]["field_help"]
        assert payload["module"]["help"]["warnings"] == [
            "Cloud sync can delete remote files when the local source is wrong, so storage safety checks must pass first."
        ]
        assert payload["module"]["help"]["confirmations"] == [
            {
                "key": "run_sync",
                "text": "Run cloud backup only after the storage safety check passes.",
            }
        ]
        assert payload["module"]["help"]["error_explanations"]
        assert payload["module"]["help"]["recovery_actions"]
        assert payload["plan"] == expected_plan
        assert "available" in payload["plan"]["required_tools"][0]
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_module_plan_api_and_cli_expose_same_contract_details(tmp_path):
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        app = _create_fake_app(str(tmp_path))

        with (
            patch("simple_safer_server.core.module_checks.shutil.which", return_value=None),
            _admin_client(app),
            app.test_client() as client,
        ):
            with client.session_transaction() as session:
                session["username"] = "admin"
            api_response = client.get("/api/modules/cloud-backup/plan")
            cli_exit, cli_stdout, cli_stderr = _run_cli(["module", "plan", "cloud-backup"])

        assert api_response.status_code == 200
        assert cli_exit == 0
        assert cli_stderr == ""
        plan = api_response.get_json()["data"]["plan"]
        for resource in plan["owned_resources"]:
            assert resource["identifier"] in cli_stdout
            assert resource["reason"] in cli_stdout
        for action in plan["privileged_actions"]:
            assert action["name"] in cli_stdout
            assert action["description"] in cli_stdout
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_module_plan_fragment_renders_read_only_preview(tmp_path):
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        app = _create_fake_app(str(tmp_path))

        with (
            patch(
                "simple_safer_server.core.module_checks.shutil.which",
                return_value="/usr/bin/rclone",
            ),
            _admin_client(app),
            app.test_client() as client,
        ):
            with client.session_transaction() as session:
                session["username"] = "admin"
            response = client.get("/fragments/modules/cloud-backup/plan")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'class="module-plan-preview"' in body
        assert 'data-module-slug="cloud-backup"' in body
        assert "Cloud Backup setup plan" in body
        assert "Configure rclone with an SSS-owned config before any cloud sync runs." in body
        assert "Isolate rclone config" in body
        assert "Available" in body
        assert "/etc/SimpleSaferServer/rclone/rclone.conf" in body
        assert "cloud-backup.write-rclone-config" in body
        assert "This preview is read-only. No changes have been made to the system." in body
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_module_plan_fragment_marks_resources_recorded_after_specific_write(tmp_path):
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        app = _create_fake_app(str(tmp_path))

        with _admin_client(app), app.test_client() as client:
            with client.session_transaction() as session:
                session["username"] = "admin"
            response = client.get("/fragments/modules/storage/plan")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "/etc/fstab#SimpleSaferServer managed backup drive" in body
        assert "After specific write" in body
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_module_list_api_exposes_nav_and_route_metadata(tmp_path):
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        app = _create_fake_app(str(tmp_path))

        with _admin_client(app), app.test_client() as client:
            with client.session_transaction() as session:
                session["username"] = "admin"
            response = client.get("/api/modules")

        assert response.status_code == 200
        modules = response.get_json()["data"]["modules"]
        storage = next(module for module in modules if module["slug"] == "storage")
        assert storage["applied"] is False
        assert storage["routes"][0] == {
            "rule": "/storage",
            "endpoint": "storage_routes.storage_page",
            "methods": ["GET"],
            "page": True,
        }
        assert storage["nav_items"][0]["label"] == "Storage"
        assert storage["nav_items"][0]["active_endpoints"] == [
            "storage_routes.storage_page",
            "storage_routes.storage_change_drive_page",
            "storage_routes.storage_existing_folder_page",
        ]
        assert storage["jobs"][0]["name"] == "mount-check"
        assert storage["jobs"][0]["daily_time_offset_minutes"] == -4
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_module_list_api_marks_applied_modules_from_manifest(tmp_path):
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        app = _create_fake_app(str(tmp_path))
        services = app.extensions["simple_safer_server"]
        alerts_module = create_builtin_module_registry().module_for_slug("alerts")
        ownership_manifest_for_runtime(services.runtime).record_module_resources(
            alerts_module.slug,
            module_apply_resources(alerts_module),
        )

        with _admin_client(app), app.test_client() as client:
            with client.session_transaction() as session:
                session["username"] = "admin"
            response = client.get("/api/modules")

        assert response.status_code == 200
        modules = response.get_json()["data"]["modules"]
        alerts = next(module for module in modules if module["slug"] == "alerts")
        storage = next(module for module in modules if module["slug"] == "storage")
        assert alerts["applied"] is True
        assert storage["applied"] is False
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_module_check_api_uses_shared_check_shape(tmp_path):
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        app = _create_fake_app(str(tmp_path))

        with (
            patch("simple_safer_server.core.module_checks.shutil.which", return_value=None),
            _admin_client(app),
            app.test_client() as client,
        ):
            with client.session_transaction() as session:
                session["username"] = "admin"
            response = client.get("/api/modules/cloud-backup/check")

        assert response.status_code == 200
        payload = response.get_json()["data"]
        assert payload["module"]["slug"] == "cloud-backup"
        assert payload["check"]["module_slug"] == "cloud-backup"
        assert payload["check"]["blocking"] is True
        assert payload["check"]["required_tools"] == [
            {
                "name": "update-ca-certificates",
                "purpose": "Maintains the system CA bundle used by outbound HTTPS connections.",
                "optional": False,
                "available": False,
                "path": "",
                "blocking": True,
                "status": "missing",
            },
            {
                "name": "rclone",
                "purpose": "Runs the cloud sync after storage safety checks pass.",
                "optional": False,
                "available": False,
                "path": "",
                "blocking": True,
                "status": "missing",
            }
        ]
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_module_apply_api_records_ownership_with_lifecycle(tmp_path):
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        app = _create_fake_app(str(tmp_path))

        with (
            patch("simple_safer_server.core.module_checks.shutil.which", side_effect=_tool_path),
            _admin_client(app),
            app.test_client() as client,
        ):
            with client.session_transaction() as session:
                session["username"] = "admin"
            response = client.post("/api/modules/alerts/apply")

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["message"] == "Recorded ownership for module: alerts"
        assert [item["identifier"] for item in payload["data"]["recorded"]] == [
            "<config>/smtp.conf",
            "<config>/alerts.json",
        ]
        assert (tmp_path / "ownership.json").exists()
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_module_uninstall_api_removes_app_owned_files_and_records(tmp_path):
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        app = _create_fake_app(str(tmp_path))
        config_dir = tmp_path / "config"
        smtp_config = config_dir / "smtp.conf"
        alerts_history = config_dir / "alerts.json"
        smtp_config.write_text("smtp", encoding="utf-8")
        alerts_history.write_text("[]", encoding="utf-8")

        with (
            patch("simple_safer_server.core.module_checks.shutil.which", side_effect=_tool_path),
            _admin_client(app),
            app.test_client() as client,
        ):
            with client.session_transaction() as session:
                session["username"] = "admin"
            apply_response = client.post("/api/modules/alerts/apply")
            uninstall_response = client.post("/api/modules/alerts/uninstall")

        assert apply_response.status_code == 200
        assert uninstall_response.status_code == 200
        payload = uninstall_response.get_json()["data"]
        assert [item["identifier"] for item in payload["removed"]] == [
            "<config>/smtp.conf",
            "<config>/alerts.json",
        ]
        assert set(payload["removed_paths"]) == {str(smtp_config), str(alerts_history)}
        assert not smtp_config.exists()
        assert not alerts_history.exists()
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_read_only_module_apply_api_returns_conflict(tmp_path):
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        app = _create_fake_app(str(tmp_path))

        with _admin_client(app), app.test_client() as client:
            with client.session_transaction() as session:
                session["username"] = "admin"
            response = client.post("/api/modules/system-updates/apply")

        assert response.status_code == 409
        payload = response.get_json()
        assert payload["type"].endswith("#module-apply-not-available")
        assert "read-only" in payload["detail"]
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_module_apply_api_blocks_missing_required_tools(tmp_path):
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        app = _create_fake_app(str(tmp_path))

        with (
            patch("simple_safer_server.core.module_checks.shutil.which", return_value=None),
            _admin_client(app),
            app.test_client() as client,
        ):
            with client.session_transaction() as session:
                session["username"] = "admin"
            response = client.post("/api/modules/cloud-backup/apply")

        assert response.status_code == 409
        payload = response.get_json()
        assert payload["type"].endswith("#module-apply-not-available")
        assert "required tools are missing: update-ca-certificates, rclone" in payload["detail"]
        assert not (tmp_path / "ownership.json").exists()
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_module_api_rejects_unknown_slug(tmp_path):
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        app = _create_fake_app(str(tmp_path))

        with _admin_client(app), app.test_client() as client:
            with client.session_transaction() as session:
                session["username"] = "admin"
            response = client.get("/api/modules/missing/plan")

        assert response.status_code == 404
        assert response.get_json()["detail"] == "Unknown module: missing"
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state
