import tempfile
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from simple_safer_server.services.disabled_timers import DisabledTimerService, parse_timestamp


class FakeSystemd:
    def __init__(self):
        self.disabled = []
        self.enabled = []
        self.enable_attempts = []
        self.fail_enable = set()
        self.fail_disable = set()

    def disable_timer_now(self, timer_name):
        if timer_name in self.fail_disable:
            raise RuntimeError("disable failed")
        self.disabled.append(timer_name)

    def enable_timer_now(self, timer_name):
        self.enable_attempts.append(timer_name)
        if timer_name in self.fail_enable:
            raise RuntimeError("enable failed")
        self.enabled.append(timer_name)


def _runtime(temp_dir, is_fake=False):
    return SimpleNamespace(is_fake=is_fake, data_dir=Path(temp_dir))


def _config():
    return {
        "system": {"setup_complete": "true"},
        "storage": {"mode": "managed_drive"},
        "backup": {"cloud_enabled": "true"},
    }


def test_disable_writes_state_after_systemd_success_and_replaces_existing_state():
    with tempfile.TemporaryDirectory() as temp_dir:
        systemd = FakeSystemd()
        service = DisabledTimerService(_runtime(temp_dir), systemd)
        expires_at = datetime(2026, 5, 13, 18, 0, 0, tzinfo=UTC)

        service.disable(
            "Cloud Backup", "backup_cloud.timer", mode="temporary", expires_at=expires_at
        )
        service.disable("Cloud Backup", "backup_cloud.timer", mode="permanent")

        assert systemd.disabled == ["backup_cloud.timer", "backup_cloud.timer"]
        record = service.get_record("backup_cloud.timer")
        assert record is not None
        assert record["mode"] == "permanent"
        assert record["created_at"].endswith("+00:00")
        assert "expires_at" not in record


def test_disable_rejects_naive_temporary_expiration():
    with tempfile.TemporaryDirectory() as temp_dir:
        systemd = FakeSystemd()
        service = DisabledTimerService(_runtime(temp_dir), systemd)

        try:
            service.disable(
                "Cloud Backup",
                "backup_cloud.timer",
                mode="temporary",
                expires_at=datetime(2026, 5, 13, 18, 0, 0),
            )
            raise AssertionError("naive temporary expiration was accepted")
        except ValueError as exc:
            assert "timezone offset" in str(exc)
        assert systemd.disabled == []


def test_disable_failure_does_not_write_state():
    with tempfile.TemporaryDirectory() as temp_dir:
        systemd = FakeSystemd()
        systemd.fail_disable.add("backup_cloud.timer")
        service = DisabledTimerService(_runtime(temp_dir), systemd)

        with suppress(RuntimeError):
            service.disable("Cloud Backup", "backup_cloud.timer", mode="permanent")

        assert service.get_record("backup_cloud.timer") is None


def test_enable_runs_systemd_and_removes_state():
    with tempfile.TemporaryDirectory() as temp_dir:
        systemd = FakeSystemd()
        service = DisabledTimerService(_runtime(temp_dir), systemd)

        service.disable("Cloud Backup", "backup_cloud.timer", mode="permanent")
        service.enable("backup_cloud.timer")

        assert systemd.enabled == ["backup_cloud.timer"]
        assert service.get_record("backup_cloud.timer") is None


def test_fake_mode_records_without_invoking_systemd():
    with tempfile.TemporaryDirectory() as temp_dir:
        systemd = FakeSystemd()
        service = DisabledTimerService(_runtime(temp_dir, is_fake=True), systemd)

        service.disable("Cloud Backup", "backup_cloud.timer", mode="permanent")
        service.enable("backup_cloud.timer")

        assert systemd.disabled == []
        assert systemd.enabled == []


def test_restore_expired_temporary_records_and_leaves_future_and_permanent_records():
    with tempfile.TemporaryDirectory() as temp_dir:
        systemd = FakeSystemd()
        service = DisabledTimerService(_runtime(temp_dir), systemd)
        now = datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC)

        service.disable(
            "Cloud Backup",
            "backup_cloud.timer",
            mode="temporary",
            expires_at=now - timedelta(minutes=1),
        )
        service.disable(
            "DDNS Update",
            "ddns_update.timer",
            mode="temporary",
            expires_at=now + timedelta(minutes=1),
        )
        service.disable("App Update", "app_update.timer", mode="permanent")

        result = service.restore_expired(_config(), now=now)

        assert result["restored"] == ["backup_cloud.timer"]
        assert systemd.enabled == ["backup_cloud.timer"]
        assert service.get_record("backup_cloud.timer") is None
        assert service.get_record("ddns_update.timer") is not None
        assert service.get_record("app_update.timer") is not None


def test_restore_failures_retry_three_times_then_alert_once_and_stop_retrying():
    with tempfile.TemporaryDirectory() as temp_dir:
        systemd = FakeSystemd()
        systemd.fail_enable.add("backup_cloud.timer")
        alert_notifier = MagicMock()
        service = DisabledTimerService(_runtime(temp_dir), systemd, alert_notifier=alert_notifier)
        now = datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC)

        service.disable("Cloud Backup", "backup_cloud.timer", mode="temporary", expires_at=now)

        service.restore_expired(_config(), now=now)
        service.restore_expired(_config(), now=now + timedelta(minutes=5))
        service.restore_expired(_config(), now=now + timedelta(minutes=10))
        service.restore_expired(_config(), now=now + timedelta(minutes=15))

        record = service.get_record("backup_cloud.timer")
        assert record is not None
        assert record["restore_failed"] is True
        assert record["restore_attempts"] == 3
        assert record["last_restore_attempt_at"].endswith("+00:00")
        assert len(systemd.enable_attempts) == 3
        alert_notifier.notify.assert_called_once()


@pytest.mark.parametrize(
    ("timer_name", "section", "key", "value"),
    [
        ("check_mount.timer", "storage", "mode", "existing_folder"),
        ("backup_cloud.timer", "backup", "cloud_enabled", "false"),
    ],
)
def test_expired_pause_does_not_restart_task_disabled_by_config(
    tmp_path, timer_name, section, key, value
):
    systemd = FakeSystemd()
    service = DisabledTimerService(_runtime(tmp_path), systemd)
    now = datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC)
    service.disable("Paused task", timer_name, mode="temporary", expires_at=now)
    service.disable("DDNS Update", "ddns_update.timer", mode="temporary", expires_at=now)
    config = _config()
    config[section][key] = value

    # The periodic helper runs in a new process and must use the current config,
    # rather than treating the saved pause as permission to restart any task.
    restorer = DisabledTimerService(_runtime(tmp_path), systemd)
    result = restorer.restore_expired(config, now=now)

    assert systemd.enabled == ["ddns_update.timer"]
    assert result == {"restored": ["ddns_update.timer"], "failed": []}
    assert restorer.get_record(timer_name) is None


def test_expired_pause_waits_for_setup_completion(tmp_path):
    systemd = FakeSystemd()
    service = DisabledTimerService(_runtime(tmp_path), systemd)
    now = datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC)
    service.disable("Cloud Backup", "backup_cloud.timer", mode="temporary", expires_at=now)
    config = _config()
    config["system"]["setup_complete"] = "false"

    assert service.restore_expired(config, now=now) == {"restored": [], "failed": []}
    assert systemd.enabled == []
    assert service.get_record("backup_cloud.timer") is not None

    config["system"]["setup_complete"] = "true"
    service.restore_expired(config, now=now)

    assert systemd.enabled == ["backup_cloud.timer"]
    assert service.get_record("backup_cloud.timer") is None


def test_parse_timestamp_rejects_naive_state_values():
    try:
        parse_timestamp("2026-05-13T12:00:00")
        raise AssertionError("naive timestamp was accepted")
    except ValueError as exc:
        assert "timezone offset" in str(exc)
