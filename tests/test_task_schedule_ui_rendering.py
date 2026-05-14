import os
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

            # Assert solid premium button classes are used
            assert 'class="btn btn-warning btn-sm"' in page or "btn-warning" in page
            assert 'class="btn btn-primary btn-sm' in page or "btn-primary" in page

            # Assert both Disable and Enable buttons are rendered without d-none hiding
            assert 'id="disable-schedule-btn"' in page
            assert 'id="enable-schedule-btn"' in page

            enable_btn_block = page.split('id="enable-schedule-btn"')[1].split(">", 1)[0]
            assert "d-none" not in enable_btn_block

            # When default active schedule, Enable Schedule should be natively disabled
            assert "disabled" in enable_btn_block
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
