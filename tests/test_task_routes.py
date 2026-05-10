from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

from simple_safer_server.routes.tasks import tasks


def _build_app(task_service):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret"
    app.extensions["simple_safer_server"] = SimpleNamespace(
        task_service=task_service,
        config_manager=MagicMock(),
        system_utils=MagicMock(),
    )
    app.register_blueprint(tasks)
    return app


def test_task_detail_loads_maximum_log_window():
    task = MagicMock()
    task.name = "App Update"
    task.status = "Success"
    task.get_logs.return_value = "full log"
    task_service = MagicMock()
    task_service.get_task.return_value = task
    app = _build_app(task_service)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with patch(
        "simple_safer_server.services.user_manager.UserManager", return_value=user_manager
    ), patch(
        "simple_safer_server.routes.tasks.render_template", return_value="rendered"
    ) as render, app.test_client() as client:
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.get("/task/App%20Update")

    assert response.status_code == 200
    task.get_logs.assert_called_once_with(500)
    assert render.call_args.kwargs["log_lines"] == 500


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

    with patch(
        "simple_safer_server.services.user_manager.UserManager", return_value=user_manager
    ), app.test_client() as client:
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

    with patch(
        "simple_safer_server.services.user_manager.UserManager", return_value=user_manager
    ), app.test_client() as client:
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.get("/api/tasks/Missing/status")

    assert response.status_code == 404
    assert response.get_json()["type"].endswith("#task-not-found")
