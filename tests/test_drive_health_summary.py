import os
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from simple_safer_server.services import drive_health as drive_health_service
from simple_safer_server.services import runtime
from simple_safer_server.services.drive_health import DriveHealthSummaryService


def _create_fake_app():
    previous_runtime = runtime._runtime
    previous_fake_state = runtime._fake_state
    temp_dir = TemporaryDirectory()
    patcher = patch.dict(
        os.environ,
        {
            "SSS_MODE": "fake",
            "SSS_SKIP_LOGIN": "true",
            "SSS_DATA_DIR": temp_dir.name,
        },
        clear=False,
    )
    patcher.start()
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

    def cleanup():
        patcher.stop()
        temp_dir.cleanup()
        runtime._runtime = previous_runtime
        runtime._fake_state = previous_fake_state

    return app, cleanup


def test_drive_health_summary_starts_with_no_check_yet():
    app, cleanup = _create_fake_app()
    try:
        with app.test_client() as client:
            response = client.get("/api/drive_health/summary")

        assert response.status_code == 200
        assert response.get_json()["data"]["detail"] == "No check yet"
        assert response.get_json()["data"]["checked_at"] is None
    finally:
        cleanup()


def test_drive_health_summary_get_does_not_probe_drive():
    app, cleanup = _create_fake_app()
    try:
        with patch(
            "simple_safer_server.routes.drive_health.get_smart_attributes",
            side_effect=AssertionError("GET summary must not probe SMART"),
        ):
            with app.test_client() as client:
                response = client.get("/api/drive_health/summary")

        assert response.status_code == 200
        assert response.get_json()["data"]["detail"] == "No check yet"
    finally:
        cleanup()


def test_drive_health_page_renders_warning_when_smartctl_support_check_fails():
    from simple_safer_server.routes import drive_health as route_module

    services = SimpleNamespace(
        runtime=SimpleNamespace(is_fake=False, default_mount_point="/media/backup"),
        config_manager=SimpleNamespace(get_value=lambda _section, _key, default="": default),
        system_utils=SimpleNamespace(),
    )
    app = Flask(__name__)

    with app.test_request_context("/drives"):
        with patch("simple_safer_server.routes.drive_health._get_services", return_value=services):
            with patch(
                "simple_safer_server.routes.drive_health.get_hdsentinel_settings",
                return_value={"enabled": False, "health_change_alert": False},
            ):
                with patch(
                    "simple_safer_server.routes.drive_health.get_smartctl_json_support",
                    side_effect=subprocess.TimeoutExpired(["smartctl", "-h"], 60),
                ):
                    with patch(
                        "simple_safer_server.routes.drive_health.render_template",
                        return_value="rendered",
                    ) as mock_render:
                        response = route_module.drives.__wrapped__()

    assert response == "rendered"
    _args, kwargs = mock_render.call_args
    warning = kwargs["smart_support_warning"]
    assert "Could not check smartctl JSON support:" in warning
    assert "timed out" in warning


def test_drive_health_manual_check_shows_smart_details_without_failure_score():
    app, cleanup = _create_fake_app()
    smart = {"smart_194_raw": 32.0}
    try:
        with patch(
            "simple_safer_server.routes.drive_health.get_smart_attributes",
            return_value=(smart, [], None),
        ):
            with app.test_client() as client:
                response = client.post("/drives", data={"form_action": "run_health_check"})

        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert '<div class="alert alert-danger">' not in html
        assert "SMART Data" in html
        assert "smart_194_raw" in html
        assert "Failure probability" not in html
    finally:
        cleanup()


def test_drive_health_settings_save_does_not_probe_hdsentinel():
    app, cleanup = _create_fake_app()
    try:
        with patch(
            "simple_safer_server.routes.drive_health.collect_hdsentinel_snapshot",
            side_effect=AssertionError("settings save must not probe HDSentinel"),
        ):
            with app.test_client() as client:
                response = client.post(
                    "/drives",
                    data={
                        "form_action": "save_hdsentinel_settings",
                        "hdsentinel_enabled": "on",
                    },
                )

        assert response.status_code == 200
        assert b"HDSentinel settings saved successfully." in response.data
    finally:
        cleanup()


def test_drive_health_manual_check_ignores_stale_hdsentinel_state_when_disabled():
    app, cleanup = _create_fake_app()
    try:
        with app.app_context():
            services = app.extensions["simple_safer_server"]
            services.config_manager.set_value("hdsentinel", "enabled", "false")
            drive_health_service.save_hdsentinel_state(
                {"available": True, "health_pct": 10, "performance_pct": 90},
                runtime=services.runtime,
            )
        with patch(
            "simple_safer_server.routes.drive_health.get_smart_attributes",
            return_value=({"smart_194_raw": 32.0}, [], None),
        ):
            with app.test_client() as client:
                response = client.post("/drives", data={"form_action": "run_health_check"})
                summary = client.get("/api/drive_health/summary")

        assert response.status_code == 200
        data = summary.get_json()["data"]
        assert data["status"] == "unknown"
        assert data["hdsentinel_health"] is None
        assert data["detail"] == "SMART details were collected."
    finally:
        cleanup()


def test_drive_health_refresh_probes_and_updates_ram_summary():
    app, cleanup = _create_fake_app()
    try:
        with patch(
            "simple_safer_server.services.drive_health.get_smart_attributes",
            return_value=({"smart_194_raw": 32.0}, [], None),
        ) as mock_smart:
            with patch(
                "simple_safer_server.services.drive_health.collect_hdsentinel_snapshot",
                return_value={
                    "available": True,
                    "health_pct": 99,
                    "performance_pct": 98,
                    "temperature_c": 31,
                },
            ):
                with app.test_client() as client:
                    refresh = client.post("/api/drive_health/refresh")
                    summary = client.get("/api/drive_health/summary")

        assert refresh.status_code == 200
        assert refresh.get_json()["data"]["status"] == "good"
        assert summary.get_json()["data"]["hdsentinel_health"] == 99
        assert summary.get_json()["data"]["detail"] == "HDSentinel health: 99%."
        mock_smart.assert_called_once()
    finally:
        cleanup()


def test_drive_health_refresh_ignores_hdsentinel_without_health_percentage():
    app, cleanup = _create_fake_app()
    try:
        with patch(
            "simple_safer_server.services.drive_health.get_smart_attributes",
            return_value=({"smart_194_raw": 32.0}, [], None),
        ):
            with patch(
                "simple_safer_server.services.drive_health.collect_hdsentinel_snapshot",
                return_value={
                    "available": True,
                    "health_pct": None,
                    "performance_pct": 91,
                    "temperature_c": 31,
                },
            ):
                with app.test_client() as client:
                    response = client.post("/api/drive_health/refresh")

        data = response.get_json()["data"]
        assert response.status_code == 200
        assert data["status"] == "unknown"
        assert data["hdsentinel_health"] is None
        assert data["detail"] == "SMART details were collected."
    finally:
        cleanup()


def test_drive_health_timeout_summary_stays_neutral():
    app, cleanup = _create_fake_app()
    try:
        with patch(
            "simple_safer_server.services.drive_health.get_smart_attributes",
            return_value=(None, None, "The drive health check timed out."),
        ):
            with patch(
                "simple_safer_server.services.drive_health.collect_hdsentinel_snapshot",
                return_value={"available": False, "error": "timeout"},
            ):
                with app.test_client() as client:
                    response = client.post("/api/drive_health/refresh")

        data = response.get_json()["data"]
        assert response.status_code == 200
        assert data["status"] == "unknown"
        assert data["detail"] == "timeout"
    finally:
        cleanup()


def test_drive_health_refresh_uses_hdsentinel_warning_threshold():
    app, cleanup = _create_fake_app()
    try:
        with patch(
            "simple_safer_server.services.drive_health.get_smart_attributes",
            return_value=({"smart_194_raw": 32.0}, [], None),
        ):
            with patch(
                "simple_safer_server.services.drive_health.collect_hdsentinel_snapshot",
                return_value={
                    "available": True,
                    "health_pct": 42,
                    "performance_pct": 91,
                    "temperature_c": 31,
                },
            ):
                with app.test_client() as client:
                    response = client.post("/api/drive_health/refresh")

        data = response.get_json()["data"]
        assert response.status_code == 200
        assert data["status"] == "warning"
        assert data["detail"] == "HDSentinel health: 42%."
        assert data["hdsentinel_health"] == 42
    finally:
        cleanup()


def test_drive_health_summary_service_keeps_only_latest_summary():
    service = DriveHealthSummaryService()
    service.publish({"status": "good", "hdsentinel_health": 99, "checked_at": "first"})
    service.publish({"status": "warning", "hdsentinel_health": 42, "checked_at": "second"})

    summary = service.get_summary()
    assert summary["status"] == "warning"
    assert summary["hdsentinel_health"] == 42
    assert summary["checked_at"] == "second"


def test_drive_health_summary_service_accepts_later_publish_with_same_timestamp():
    service = DriveHealthSummaryService()
    checked_at = "2026-05-02T14:05:00"

    service.publish({"status": "good", "hdsentinel_health": 99, "checked_at": checked_at})
    latest = service.publish(
        {"status": "warning", "hdsentinel_health": 42, "checked_at": checked_at}
    )

    assert latest["status"] == "warning"
    assert "_publish_seq" not in latest
    assert service.get_summary()["hdsentinel_health"] == 42
