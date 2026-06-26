from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from flask import Flask

from simple_safer_server.core.module_lifecycle import ModuleLifecycleError
from simple_safer_server.routes.tasks import tasks
from simple_safer_server.services.task_service import TASK_LOG_LINE_LIMIT


def _build_app(task_service):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret"
    app.extensions["simple_safer_server"] = SimpleNamespace(
        task_service=task_service,
        config_manager=MagicMock(),
        system_utils=MagicMock(),
    )

    @app.route("/login")
    def login():
        return "login"

    app.register_blueprint(tasks)
    return app


def _build_dashboard_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret"
    config_manager = MagicMock()
    config_manager.is_setup_complete.return_value = True
    config_manager.get_all_config.return_value = {
        "backup": {"cloud_enabled": "false", "mount_point": "/srv/storage"},
        "storage": {"mode": "existing_folder", "path": "/srv/storage", "storage_id": "id"},
    }
    app.extensions["simple_safer_server"] = SimpleNamespace(
        task_service=SimpleNamespace(task_summaries=list),
        config_manager=config_manager,
        system_utils=MagicMock(),
        runtime=SimpleNamespace(is_fake=True, default_mount_point="/media/backup"),
    )
    app.add_url_rule("/login", "login", lambda: "login")
    app.register_blueprint(tasks)
    return app


def test_dashboard_marks_existing_folder_unavailable_when_disk_usage_fails():
    app = _build_dashboard_app()
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with (
        patch("simple_safer_server.services.user_manager.UserManager", return_value=user_manager),
        patch("simple_safer_server.routes.tasks.psutil.disk_usage", side_effect=OSError),
        patch("simple_safer_server.routes.tasks.psutil.cpu_percent", return_value=12),
        patch(
            "simple_safer_server.routes.tasks.psutil.virtual_memory",
            return_value=SimpleNamespace(percent=34),
        ),
        patch(
            "simple_safer_server.routes.tasks.render_template", return_value="rendered"
        ) as render,
        app.test_client() as client,
    ):
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.get("/dashboard")

    assert response.status_code == 200
    mount_info = render.call_args.kwargs["mount_info"]
    assert mount_info["available"] is False
    assert mount_info["disk_available"] is False
    assert mount_info["error"] == "Storage path is not readable."


def test_task_detail_loads_maximum_log_window():
    task = MagicMock()
    task.name = "App Update"
    task.status = "Success"
    task.get_logs.return_value = "full log"
    task_service = MagicMock()
    task_service.get_task.return_value = task
    task_service.task_summary.return_value = {"schedule": {"state": "active"}}
    app = _build_app(task_service)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with (
        patch("simple_safer_server.services.user_manager.UserManager", return_value=user_manager),
        patch(
            "simple_safer_server.routes.tasks.render_template", return_value="rendered"
        ) as render,
        app.test_client() as client,
    ):
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.get("/task/App%20Update")

    assert response.status_code == 200
    task.get_logs.assert_called_once_with(TASK_LOG_LINE_LIMIT)
    assert render.call_args[1]["log_lines"] == TASK_LOG_LINE_LIMIT
    assert render.call_args[1]["task_summary"] == {"schedule": {"state": "active"}}
    assert render.call_args[1]["task_detail_ui_text"]["refresh"] == {
        "reconnecting": "Reconnecting to log...",
        "retrying": "Log refresh paused; retrying...",
    }


def test_task_logs_defaults_to_global_log_window():
    task = MagicMock()
    task.get_logs.return_value = "full log"
    task_service = MagicMock()
    task_service.get_task.return_value = task
    app = _build_app(task_service)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with (
        patch("simple_safer_server.services.user_manager.UserManager", return_value=user_manager),
        app.test_client() as client,
    ):
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.get("/task/App%20Update/logs")

    assert response.status_code == 200
    assert response.text == "full log"
    task.get_logs.assert_called_once_with(TASK_LOG_LINE_LIMIT)


def test_task_logs_clamps_invalid_and_oversized_windows_to_global_limit():
    task = MagicMock()
    task.get_logs.return_value = "full log"
    task_service = MagicMock()
    task_service.get_task.return_value = task
    app = _build_app(task_service)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with (
        patch("simple_safer_server.services.user_manager.UserManager", return_value=user_manager),
        app.test_client() as client,
    ):
        with client.session_transaction() as session:
            session["username"] = "admin"

        invalid_response = client.get("/task/App%20Update/logs?lines=abc")
        oversized_response = client.get("/task/App%20Update/logs?lines=999999")

    assert invalid_response.status_code == 200
    assert oversized_response.status_code == 200
    assert task.get_logs.call_args_list == [
        call(TASK_LOG_LINE_LIMIT),
        call(TASK_LOG_LINE_LIMIT),
    ]


def test_task_logs_keeps_smaller_requested_window():
    task = MagicMock()
    task.get_logs.return_value = "short log"
    task_service = MagicMock()
    task_service.get_task.return_value = task
    app = _build_app(task_service)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with (
        patch("simple_safer_server.services.user_manager.UserManager", return_value=user_manager),
        app.test_client() as client,
    ):
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.get("/task/App%20Update/logs?lines=25")

    assert response.status_code == 200
    task.get_logs.assert_called_once_with(25)


def test_task_status_returns_current_task_summary():
    task = MagicMock()
    task_service = MagicMock()
    task_service.get_task.return_value = task
    task_service.task_summary.return_value = {
        "name": "App Update",
        "next_run": "Unknown",
        "last_run": "Sun 2026-05-10 15:47:10 UTC",
        "status": "Success",
        "last_run_duration": "12s",
    }
    app = _build_app(task_service)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with (
        patch("simple_safer_server.services.user_manager.UserManager", return_value=user_manager),
        app.test_client() as client,
    ):
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.get("/api/tasks/App%20Update/status")

    assert response.status_code == 200
    assert response.get_json()["data"]["task"]["status"] == "Success"
    task_service.get_task.assert_called_once_with("App Update")
    task_service.task_summary.assert_called_once_with(task)


def test_task_status_returns_not_found_for_unknown_task():
    task_service = MagicMock()
    task_service.get_task.return_value = None
    app = _build_app(task_service)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with (
        patch("simple_safer_server.services.user_manager.UserManager", return_value=user_manager),
        app.test_client() as client,
    ):
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.get("/api/tasks/Missing/status")

    assert response.status_code == 404
    assert response.get_json()["type"].endswith("#task-not-found")


def test_task_start_returns_setup_required_for_unapplied_module():
    task = MagicMock()
    task.start.side_effect = ModuleLifecycleError(
        "Cloud Backup must be applied before it can write config."
    )
    task_service = MagicMock()
    task_service.get_task.return_value = task
    app = _build_app(task_service)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with (
        patch("simple_safer_server.services.user_manager.UserManager", return_value=user_manager),
        app.test_client() as client,
    ):
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.post(
            "/task/Cloud%20Backup/start",
            headers={"Accept": "application/json"},
        )

    assert response.status_code == 409
    assert response.get_json()["type"].endswith("#module-setup-required")
    assert "Cloud Backup must be applied" in response.get_json()["detail"]


def test_schedule_disable_and_enable_routes_are_not_registered():
    task_service = MagicMock()
    app = _build_app(task_service)

    with app.test_client() as client:
        disable_response = client.post(
            "/task/Cloud%20Backup/disable-schedule",
            json={"mode": "temporary", "hours": 6},
            headers={"Accept": "application/json"},
        )
        enable_response = client.post(
            "/task/Cloud%20Backup/enable-schedule",
            headers={"Accept": "application/json"},
        )

    assert disable_response.status_code == 404
    assert enable_response.status_code == 404
