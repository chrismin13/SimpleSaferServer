import os
from tempfile import TemporaryDirectory
from unittest.mock import patch

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

    app, _socketio = create_app()
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


def test_drive_health_refresh_probes_and_updates_ram_summary():
    app, cleanup = _create_fake_app()
    try:
        with patch(
            "simple_safer_server.services.drive_health.get_smart_attributes",
            return_value=({"smart_194_raw": 32.0}, [], None),
        ) as mock_smart:
            with patch(
                "simple_safer_server.services.drive_health.predict_failure_probability",
                return_value=0.04,
            ):
                with patch(
                    "simple_safer_server.services.drive_health.get_optimal_threshold",
                    return_value=0.5,
                ):
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
        assert summary.get_json()["data"]["probability"] == 0.04
        assert summary.get_json()["data"]["hdsentinel_health"] == 99
        mock_smart.assert_called_once()
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
        assert data["detail"] == "The drive health check timed out."
    finally:
        cleanup()


def test_drive_health_summary_service_keeps_only_latest_summary():
    service = DriveHealthSummaryService()
    service.publish({"status": "good", "probability": 0.03, "checked_at": "first"})
    service.publish({"status": "warning", "probability": 0.8, "checked_at": "second"})

    summary = service.get_summary()
    assert summary["status"] == "warning"
    assert summary["probability"] == 0.8
    assert summary["checked_at"] == "second"


def test_drive_health_summary_service_accepts_later_publish_with_same_timestamp():
    service = DriveHealthSummaryService()
    checked_at = "2026-05-02T14:05:00"

    service.publish({"status": "good", "probability": 0.03, "checked_at": checked_at})
    latest = service.publish({"status": "warning", "probability": 0.8, "checked_at": checked_at})

    assert latest["status"] == "warning"
    assert "_publish_seq" not in latest
    assert service.get_summary()["probability"] == 0.8
