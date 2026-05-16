import logging
from unittest.mock import patch

from scripts import restore_disabled_timers


class FakeService:
    result = None
    exception = None

    def __init__(self, runtime, systemd_adapter, alert_notifier=None):
        self.runtime = runtime
        self.systemd_adapter = systemd_adapter
        self.alert_notifier = alert_notifier

    def restore_expired(self):
        if self.exception:
            raise self.exception
        return self.result or {"restored": [], "failed": []}


class FakeRuntime:
    pass


def test_main_returns_zero_when_restore_check_completes(caplog):
    caplog.set_level(logging.INFO, logger=restore_disabled_timers.__name__)
    FakeService.exception = None
    FakeService.result = {"restored": ["backup_cloud.timer"], "failed": ["check_mount.timer"]}

    with patch("scripts.restore_disabled_timers.get_runtime", return_value=FakeRuntime()):
        with patch("scripts.restore_disabled_timers.ConfigManager"):
            with patch("scripts.restore_disabled_timers.SystemdAdapter"):
                with patch("scripts.restore_disabled_timers.AlertNotifier"):
                    with patch(
                        "scripts.restore_disabled_timers.DisabledTimerService",
                        FakeService,
                    ):
                        assert restore_disabled_timers.main() == 0

    assert "Disabled timer restore check completed: restored=1 failed=1" in caplog.text


def test_main_returns_nonzero_and_logs_traceback_when_restore_check_raises(caplog):
    FakeService.exception = RuntimeError("state file is unavailable")

    with patch("scripts.restore_disabled_timers.get_runtime", return_value=FakeRuntime()):
        with patch("scripts.restore_disabled_timers.ConfigManager"):
            with patch("scripts.restore_disabled_timers.SystemdAdapter"):
                with patch("scripts.restore_disabled_timers.AlertNotifier"):
                    with patch(
                        "scripts.restore_disabled_timers.DisabledTimerService",
                        FakeService,
                    ):
                        assert restore_disabled_timers.main() == 1

    assert "Disabled timer restore check failed" in caplog.text
    assert "state file is unavailable" in caplog.text
