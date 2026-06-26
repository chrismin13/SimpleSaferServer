from types import SimpleNamespace
from unittest.mock import patch

from simple_safer_server.modules.cloud_backup.runner import run_backup_job_direct


class FakeConfigManager:
    def __init__(self, storage_path, *, cloud_enabled, rclone_dir="remote:/backup"):
        self.storage_path = storage_path
        self.cloud_enabled = cloud_enabled
        self.rclone_dir = rclone_dir
        self.alerts = []

    def get_value(self, section, key, default=None):
        values = {
            ("backup", "cloud_enabled"): self.cloud_enabled,
            ("backup", "mount_point"): str(self.storage_path),
            ("backup", "rclone_dir"): self.rclone_dir,
            ("backup", "bandwidth_limit"): "",
        }
        return values.get((section, key), default)

    def get_all_config(self):
        return {
            "backup": {
                "cloud_enabled": self.cloud_enabled,
                "mount_point": str(self.storage_path),
                "rclone_dir": self.rclone_dir,
            },
            "storage": {
                "mode": "existing_folder",
                "path": str(self.storage_path),
                "storage_id": "storage-id",
            },
        }

    def log_alert(self, title, message, alert_type, source):
        self.alerts.append((title, message, alert_type, source))


class FakeProcess:
    returncode = 0

    def communicate(self):
        return "copied\n", ""


class FakeRcloneAdapter:
    def __init__(self):
        self.calls = []

    def sync(self, source, destination, *, config_path=None, bandwidth_limit=""):
        self.calls.append(
            {
                "source": source,
                "destination": destination,
                "config_path": config_path,
                "bandwidth_limit": bandwidth_limit,
            }
        )
        return FakeProcess()


def _runtime(tmp_path):
    return SimpleNamespace(
        is_fake=True,
        default_mount_point=str(tmp_path / "storage"),
        rclone_config_dir=tmp_path / "rclone",
    )


def test_cloud_backup_runner_alerts_when_cloud_enabled_is_missing(tmp_path):
    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    config = FakeConfigManager(storage_path, cloud_enabled=None)

    result = run_backup_job_direct(
        runtime=_runtime(tmp_path),
        config_manager=config,
        system_utils=object(),
        rclone_adapter=FakeRcloneAdapter(),
    )

    assert result == 1
    assert config.alerts[0][0] == "BACKUP TO CLOUD FAILED - Cloud Backup Setting Invalid"


def test_cloud_backup_runner_exits_cleanly_when_cloud_backup_is_disabled(tmp_path):
    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    config = FakeConfigManager(storage_path, cloud_enabled="false")
    rclone = FakeRcloneAdapter()

    result = run_backup_job_direct(
        runtime=_runtime(tmp_path),
        config_manager=config,
        system_utils=object(),
        rclone_adapter=rclone,
    )

    assert result == 0
    assert config.alerts == []
    assert rclone.calls == []


def test_cloud_backup_runner_validates_storage_and_runs_rclone(tmp_path):
    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    config = FakeConfigManager(storage_path, cloud_enabled="true")
    runtime = _runtime(tmp_path)
    rclone = FakeRcloneAdapter()

    with patch(
        "simple_safer_server.modules.cloud_backup.runner.validate_storage_ready_for_backup",
        return_value=SimpleNamespace(path=storage_path),
    ) as validate_storage:
        result = run_backup_job_direct(
            runtime=runtime,
            config_manager=config,
            system_utils=object(),
            rclone_adapter=rclone,
        )

    assert result == 0
    validate_storage.assert_called_once()
    assert rclone.calls == [
        {
            "source": str(storage_path),
            "destination": "remote:/backup",
            "config_path": str(runtime.rclone_config_dir / "rclone.conf"),
            "bandwidth_limit": "",
        }
    ]
