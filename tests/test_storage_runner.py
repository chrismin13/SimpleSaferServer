from types import SimpleNamespace
from unittest.mock import MagicMock

from simple_safer_server.modules.storage.runner import run_mount_check_job_direct


def test_storage_mount_check_runner_uses_storage_service(capsys):
    storage_service = SimpleNamespace(mount_dashboard_drive=MagicMock(return_value="Storage ready."))

    exit_code = run_mount_check_job_direct(
        runtime=SimpleNamespace(is_fake=True),
        config_manager=SimpleNamespace(log_alert=MagicMock()),
        system_utils=object(),
        storage_service=storage_service,
    )

    assert exit_code == 0
    storage_service.mount_dashboard_drive.assert_called_once_with()
    assert "Storage ready." in capsys.readouterr().out


def test_storage_mount_check_runner_alerts_on_failure(capsys):
    config_manager = SimpleNamespace(log_alert=MagicMock())
    storage_service = SimpleNamespace(
        mount_dashboard_drive=MagicMock(side_effect=RuntimeError("mount failed"))
    )

    exit_code = run_mount_check_job_direct(
        runtime=SimpleNamespace(is_fake=True),
        config_manager=config_manager,
        system_utils=object(),
        storage_service=storage_service,
    )

    assert exit_code == 1
    assert "mount failed" in capsys.readouterr().out
    config_manager.log_alert.assert_called_once_with(
        "Backup Source Check Failed",
        "mount failed",
        alert_type="error",
        source="check_mount",
    )
