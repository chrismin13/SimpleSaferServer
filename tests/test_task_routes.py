from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from flask import Flask

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

    with patch(
        "simple_safer_server.services.user_manager.UserManager", return_value=user_manager
    ), patch(
        "simple_safer_server.routes.tasks.render_template", return_value="rendered"
    ) as render, app.test_client() as client:
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.get("/task/App%20Update")

    assert response.status_code == 200
    task.get_logs.assert_called_once_with(TASK_LOG_LINE_LIMIT)
    assert render.call_args.kwargs["log_lines"] == TASK_LOG_LINE_LIMIT
    assert render.call_args.kwargs["task_summary"] == {"schedule": {"state": "active"}}


def test_task_logs_defaults_to_global_log_window():
    task = MagicMock()
    task.get_logs.return_value = "full log"
    task_service = MagicMock()
    task_service.get_task.return_value = task
    app = _build_app(task_service)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with patch(
        "simple_safer_server.services.user_manager.UserManager", return_value=user_manager
    ), app.test_client() as client:
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

    with patch(
        "simple_safer_server.services.user_manager.UserManager", return_value=user_manager
    ), app.test_client() as client:
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

    with patch(
        "simple_safer_server.services.user_manager.UserManager", return_value=user_manager
    ), app.test_client() as client:
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


def test_disable_schedule_route_calls_task_and_returns_updated_summary():
    task = MagicMock()
    task_service = MagicMock()
    task_service.get_task.return_value = task
    task_service.task_summary.return_value = {
        "name": "Cloud Backup",
        "schedule": {"state": "permanent"},
    }
    app = _build_app(task_service)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with patch(
        "simple_safer_server.services.user_manager.UserManager", return_value=user_manager
    ), app.test_client() as client:
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.post(
            "/task/Cloud%20Backup/disable-schedule",
            json={"mode": "temporary", "hours": 6},
            headers={"Accept": "application/json"},
        )

    assert response.status_code == 200
    task.disable_schedule.assert_called_once_with("temporary", hours=6)
    assert response.get_json()["data"]["task"]["schedule"]["state"] == "permanent"


def test_disable_schedule_route_rejects_invalid_mode_before_calling_task():
    task = MagicMock()
    task_service = MagicMock()
    task_service.get_task.return_value = task
    app = _build_app(task_service)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with patch(
        "simple_safer_server.services.user_manager.UserManager", return_value=user_manager
    ), app.test_client() as client:
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.post(
            "/task/Cloud%20Backup/disable-schedule",
            json={"mode": "", "hours": 6},
            headers={"Accept": "application/json"},
        )

    assert response.status_code == 400
    assert response.get_json()["type"].endswith("#task-schedule-validation-error")
    task.disable_schedule.assert_not_called()


def test_disable_schedule_route_rejects_invalid_hours_before_calling_task():
    task = MagicMock()
    task_service = MagicMock()
    task_service.get_task.return_value = task
    app = _build_app(task_service)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with patch(
        "simple_safer_server.services.user_manager.UserManager", return_value=user_manager
    ), app.test_client() as client:
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.post(
            "/task/Cloud%20Backup/disable-schedule",
            json={"mode": "temporary", "hours": "abc"},
            headers={"Accept": "application/json"},
        )

    assert response.status_code == 400
    assert response.get_json()["type"].endswith("#task-schedule-validation-error")
    task.disable_schedule.assert_not_called()


def test_disable_schedule_route_rejects_non_positive_hours_before_calling_task():
    task = MagicMock()
    task_service = MagicMock()
    task_service.get_task.return_value = task
    app = _build_app(task_service)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with patch(
        "simple_safer_server.services.user_manager.UserManager", return_value=user_manager
    ), app.test_client() as client:
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.post(
            "/task/Cloud%20Backup/disable-schedule",
            json={"mode": "temporary", "hours": 0},
            headers={"Accept": "application/json"},
        )

    assert response.status_code == 400
    assert response.get_json()["type"].endswith("#task-schedule-validation-error")
    task.disable_schedule.assert_not_called()


def test_enable_schedule_route_calls_task_and_returns_updated_summary():
    task = MagicMock()
    task_service = MagicMock()
    task_service.get_task.return_value = task
    task_service.task_summary.return_value = {
        "name": "Cloud Backup",
        "schedule": {"state": "active"},
    }
    app = _build_app(task_service)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with patch(
        "simple_safer_server.services.user_manager.UserManager", return_value=user_manager
    ), app.test_client() as client:
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.post(
            "/task/Cloud%20Backup/enable-schedule",
            headers={"Accept": "application/json"},
        )

    assert response.status_code == 200
    task.enable_schedule.assert_called_once_with()
    assert response.get_json()["data"]["task"]["schedule"]["state"] == "active"


def test_disable_schedule_route_returns_not_found_for_unknown_task():
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

        response = client.post(
            "/task/Missing/disable-schedule",
            json={"mode": "permanent"},
            headers={"Accept": "application/json"},
        )

    assert response.status_code == 404
    assert response.get_json()["type"].endswith("#task-not-found")


def test_disable_schedule_route_returns_json_login_required_for_anonymous_fetch():
    task_service = MagicMock()
    app = _build_app(task_service)

    with app.test_client() as client:
        response = client.post(
            "/task/Cloud%20Backup/disable-schedule",
            json={"mode": "temporary", "hours": 6},
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )

    assert response.status_code == 401
    assert response.is_json
    assert response.get_json()["type"].endswith("#api-login-required")


def test_enable_schedule_route_returns_json_admin_required_for_demoted_fetch_session():
    task_service = MagicMock()
    app = _build_app(task_service)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = False

    with patch(
        "simple_safer_server.services.user_manager.UserManager", return_value=user_manager
    ), app.test_client() as client:
        with client.session_transaction() as session:
            session["username"] = "operator"

        response = client.post(
            "/task/Cloud%20Backup/enable-schedule",
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )

        # A role change after login leaves a valid signed cookie, so JSON
        # callers need a 403 Problem Details response instead of a login page.
        with client.session_transaction() as session:
            assert "username" not in session

    assert response.status_code == 403
    assert response.is_json
    assert response.get_json()["type"].endswith("#api-admin-required")
    user_manager.is_admin.assert_called_once_with("operator")


def test_enable_schedule_route_reports_operation_failure():
    task = MagicMock()
    task.enable_schedule.side_effect = RuntimeError("boom")
    task_service = MagicMock()
    task_service.get_task.return_value = task
    app = _build_app(task_service)
    user_manager = MagicMock()
    user_manager.is_admin.return_value = True

    with patch(
        "simple_safer_server.services.user_manager.UserManager", return_value=user_manager
    ), app.test_client() as client:
        with client.session_transaction() as session:
            session["username"] = "admin"

        response = client.post(
            "/task/Cloud%20Backup/enable-schedule",
            headers={"Accept": "application/json"},
        )

    assert response.status_code == 500
    assert response.get_json()["type"].endswith("#task-operation-failed")
