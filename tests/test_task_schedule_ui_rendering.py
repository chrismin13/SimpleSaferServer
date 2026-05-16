import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from simple_safer_server.services import runtime


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

        app, _socketio = create_app()
        app.config["TESTING"] = True

        with app.app_context():
            services = app.extensions["simple_safer_server"]
            services.config_manager.set_value("system", "setup_complete", "true")
            services.config_manager.set_value("system", "username", "admin")
            services.user_manager.create_user("admin", "password", is_admin=True)

        return app


def test_task_detail_renders_stable_schedule_toolbar_buttons():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)

            with app.test_client() as client:
                response = client.get("/task/Cloud%20Backup")

            assert response.status_code == 200
            page = response.get_data(as_text=True)

            # Assert persistent Manage Schedule dropdown button is rendered
            assert 'id="manage-schedule-btn"' in page
            manage_btn_block = page.split('id="manage-schedule-btn"')[1].split(">", 1)[0]
            assert 'aria-haspopup="menu"' in manage_btn_block
            assert "d-none" not in manage_btn_block

            # Assert separate controls are completely eliminated
            assert 'id="disable-schedule-btn"' not in page
            assert 'id="enable-schedule-btn"' not in page
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_task_detail_renders_strict_custom_duration_modal():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)

            with app.test_client() as client:
                response = client.get("/task/Cloud%20Backup")

            assert response.status_code == 200
            page = response.get_data(as_text=True)

            # Assert custom radio option is present
            assert 'value="custom"' in page
            assert "Custom" in page.split('value="custom"')[1].split("</label>")[0]

            # Assert arrowless strict numeric input field attributes matching SMTP port
            assert 'id="disableScheduleCustomHours"' in page
            custom_input_block = page.split('id="disableScheduleCustomHours"')[1].split(">", 1)[0]
            assert 'inputmode="numeric"' in custom_input_block
            assert 'pattern="[0-9]*"' in custom_input_block
            assert 'value="48"' in custom_input_block or 'placeholder="48"' in custom_input_block

            # Assert standardized modal footer structure
            assert "modal-footer-actions" in page
            assert "modal-footer-message" in page
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_task_detail_uses_shared_task_schedule_control_modal():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)

            with app.test_client() as client:
                response = client.get("/task/Cloud%20Backup")

            assert response.status_code == 200
            page = response.get_data(as_text=True)

            assert 'data-task-schedule-control="disable-modal"' in page
            assert 'static/js/task_schedule_control.js' in page
            assert "disableScheduleDuration" in page
            assert "disableScheduleCustomHours" in page
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_dashboard_uses_shared_task_schedule_control_modal():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)

            with app.test_client() as client:
                response = client.get("/dashboard")

            assert response.status_code == 200
            page = response.get_data(as_text=True)

            assert 'data-task-schedule-control="disable-modal"' in page
            assert 'static/js/task_schedule_control.js' in page
            assert "TaskScheduleControl.createDisableScheduleController" in page
            assert "disableScheduleDuration" in page
            assert "disableScheduleCustomHours" in page
            assert 'id="dashboardDisableScheduleModal"' not in page
            assert 'name="dashboardDisableScheduleDuration"' not in page
            assert "selectedDashboardDisableDuration" not in page
            assert "disableScheduleFromDashboard" not in page
            assert "openDashboardDisableScheduleModal" not in page
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_dashboard_task_context_menu_uses_shared_action_menu():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)

            with app.test_client() as client:
                response = client.get("/dashboard")

            assert response.status_code == 200
            page = response.get_data(as_text=True)

            assert 'id="taskContextMenu"' not in page
            assert "task-context-menu" not in page
            assert "task-context-menu-item" not in page
            assert "ActionContextMenu.bind" in page
            assert "Start" in page
            assert "Stop" in page
            assert "Disable Schedule" in page
            assert "Enable Schedule" in page
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_dashboard_passive_task_refresh_keeps_open_context_menu():
    dashboard_template = Path("templates/dashboard.html").read_text(encoding="utf-8")
    update_task_schedule = dashboard_template.split("async function updateTaskSchedule()", 1)[1].split(
        "function renderDriveActionForm", 1
    )[0]

    assert "ActionContextMenu.hide()" not in update_task_schedule
    assert "setInterval(updateTaskSchedule, 5000)" in dashboard_template


def test_dashboard_only_task_context_menu_selectors_are_removed():
    dashboard_template = Path("templates/dashboard.html").read_text(encoding="utf-8")
    styles_css = Path("static/css/styles.css").read_text(encoding="utf-8")

    assert "taskContextMenu" not in dashboard_template
    assert "task-context-menu" not in dashboard_template
    assert "task-context-menu" not in styles_css


def test_disabled_task_schedule_is_dangerous_on_task_detail_and_dashboard():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)

            with app.app_context():
                services = app.extensions["simple_safer_server"]
                task = services.task_service.get_task("Cloud Backup")
                assert task is not None
                task.disable_schedule("permanent")

            with app.test_client() as client:
                detail_response = client.get("/task/Cloud%20Backup")
                dashboard_response = client.get("/dashboard")

            assert detail_response.status_code == 200
            assert dashboard_response.status_code == 200
            detail_page = detail_response.get_data(as_text=True)
            dashboard_page = dashboard_response.get_data(as_text=True)

            assert 'id="task-schedule-badge"' in detail_page
            schedule_badge = detail_page.split('id="task-schedule-badge"')[0].rsplit("<span", 1)[-1]
            assert "badge-schedule-danger" in schedule_badge
            assert "fa-calendar-xmark" in detail_page
            manage_button = detail_page.split('id="manage-schedule-btn"')[1].split(">", 1)[0]
            assert 'data-schedule-can-enable="true"' in manage_button

            assert "task-schedule-danger" in dashboard_page
            assert "Disabled" in dashboard_page
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_schedule_issue_is_warning_and_active_schedule_stays_neutral():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)

            with app.test_client() as client:
                active_response = client.get("/task/Cloud%20Backup")

            assert active_response.status_code == 200
            active_page = active_response.get_data(as_text=True)
            active_badge = active_page.split('id="task-schedule-badge"')[0].rsplit("<span", 1)[-1]
            assert "badge-neutral" in active_badge
            assert "badge-schedule-danger" not in active_badge
            assert "fa-calendar-days" in active_page

            with app.app_context():
                services = app.extensions["simple_safer_server"]
                task = services.task_service.get_task("Cloud Backup")
                assert task is not None
                original_schedule_state = services.task_service.schedule_state

                def issue_schedule_state(candidate):
                    if candidate.name == "Cloud Backup":
                        return {
                            "state": "issue",
                            "label": "Schedule issue",
                            "source": "systemd",
                            "raw_next_run": "",
                            "raw": "broken timer",
                            "guidance": "Inspect systemd.",
                            "can_disable": True,
                            "can_enable": True,
                        }
                    return original_schedule_state(candidate)

                services.task_service.schedule_state = issue_schedule_state

            with app.test_client() as client:
                issue_detail_response = client.get("/task/Cloud%20Backup")
                issue_dashboard_response = client.get("/dashboard")

            assert issue_detail_response.status_code == 200
            assert issue_dashboard_response.status_code == 200
            issue_detail_page = issue_detail_response.get_data(as_text=True)
            issue_dashboard_page = issue_dashboard_response.get_data(as_text=True)
            issue_badge = issue_detail_page.split('id="task-schedule-badge"')[0].rsplit("<span", 1)[
                -1
            ]

            assert "badge-schedule-warning" in issue_badge
            assert "badge-schedule-danger" not in issue_badge
            assert "fa-triangle-exclamation" in issue_detail_page
            issue_cell = issue_dashboard_page.split("Schedule issue")[0].rsplit("<td", 1)[-1]
            assert "task-schedule-warning" in issue_cell
            assert "task-schedule-danger" not in issue_cell
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state


def test_task_detail_schedule_menu_script_does_not_reference_removed_enable_button():
    scripts_js = Path("static/js/scripts.js").read_text(encoding="utf-8")

    assert 'id="enable-schedule-btn"' not in scripts_js
    assert "enableScheduleBtn" not in scripts_js


def test_task_detail_script_delegates_disable_schedule_flow_to_shared_controller():
    scripts_js = Path("static/js/scripts.js").read_text(encoding="utf-8")
    shared_schedule_js = Path("static/js/task_schedule_control.js").read_text(encoding="utf-8")

    assert "TaskScheduleControl.createDisableScheduleController" in scripts_js
    assert "/disable-schedule" not in scripts_js
    assert 'input[name="disableScheduleDuration"]' not in scripts_js
    assert "/disable-schedule" in shared_schedule_js
    assert 'input[name="disableScheduleDuration"]' in shared_schedule_js


def test_shared_task_schedule_controller_validates_custom_duration():
    shared_schedule_js = Path("static/js/task_schedule_control.js").read_text(encoding="utf-8")

    assert "Custom duration must contain only digits." in shared_schedule_js
    assert "Custom duration must be greater than 0 hours." in shared_schedule_js
    assert "/^\\d+$/.test(customVal)" in shared_schedule_js
    assert "hours <= 0" in shared_schedule_js


def test_system_updates_application_card_owns_source_controls():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    try:
        with TemporaryDirectory() as temp_dir:
            app = _create_fake_app(temp_dir)

            with app.test_client() as client:
                response = client.get("/system_updates")

            assert response.status_code == 200
            page = response.get_data(as_text=True)

            assert page.count('class="system-updates-panel system-updates-app-panel"') == 1
            assert (
                "<span><i class=\"fas fa-code-branch\"></i> Application Source</span>" not in page
            )

            app_card = page.split('class="system-updates-panel system-updates-app-panel"', 1)[1]
            app_card = app_card.split("</section>", 1)[0]

            assert 'id="app-update-switch-main-btn"' in app_card
            assert 'id="app-update-switch-main-tooltip"' in app_card
            assert 'id="app-branch-advanced-trigger"' in app_card
            assert 'id="appBranchAdvanced"' in app_card
            assert 'id="app-branch-switch-form"' in app_card
            assert 'id="app-branch-select"' in app_card
    finally:
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state
