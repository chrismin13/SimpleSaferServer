from types import SimpleNamespace
from unittest.mock import patch

from simple_safer_server.modules.drive_health.runner import run_drive_health_job_direct


def test_drive_health_runner_prints_scheduled_check_summary(capsys):
    result = {
        "device": "/dev/sdb",
        "smart": {"health": "ok"},
        "hdsentinel": {
            "snapshot": {
                "available": True,
                "health_pct": 98,
                "performance_pct": 100,
                "temperature_c": 34,
            }
        },
    }

    with patch(
        "simple_safer_server.modules.drive_health.runner.run_scheduled_drive_health_check",
        return_value=result,
    ) as run_check:
        exit_code = run_drive_health_job_direct(
            runtime=SimpleNamespace(),
            config_manager=object(),
            system_utils=object(),
        )

    assert exit_code == 0
    run_check.assert_called_once()
    output = capsys.readouterr().out
    assert "SMART details collected for /dev/sdb." in output
    assert "HDSentinel: health 98%, performance 100%, temperature 34C" in output


def test_drive_health_runner_returns_failure_when_check_raises(capsys):
    with patch(
        "simple_safer_server.modules.drive_health.runner.run_scheduled_drive_health_check",
        side_effect=RuntimeError("health check failed"),
    ):
        exit_code = run_drive_health_job_direct(
            runtime=SimpleNamespace(),
            config_manager=object(),
            system_utils=object(),
        )

    assert exit_code == 1
    assert "health check failed" in capsys.readouterr().out
