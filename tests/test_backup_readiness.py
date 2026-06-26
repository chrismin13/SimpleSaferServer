from types import SimpleNamespace

from simple_safer_server.core.backup_readiness import build_backup_readiness


class FakeConfigManager:
    def __init__(self, config):
        self.config = config
        self.load_calls = 0

    def load_config(self):
        self.load_calls += 1

    def get_all_config(self):
        return self.config


class FakeSmbManager:
    def __init__(self, shares):
        self.shares = shares

    def list_managed_shares(self):
        return self.shares


def _runtime(tmp_path):
    return SimpleNamespace(smtp_config_path=tmp_path / "smtp.conf")


def _base_config():
    return {
        "backup": {
            "mount_point": "/srv/backups",
            "email_address": "",
            "from_address": "",
            "cloud_enabled": "false",
            "cloud_skipped": "false",
            "rclone_dir": "",
        },
        "storage": {
            "mode": "existing_folder",
            "path": "/srv/backups",
            "storage_id": "",
        },
        "schedule": {"backup_cloud_time": "03:00", "configured": "false"},
    }


def test_backup_readiness_starts_incomplete(tmp_path):
    config = FakeConfigManager(_base_config())

    readiness = build_backup_readiness(
        config,
        runtime=_runtime(tmp_path),
        smb_manager=FakeSmbManager([]),
    )

    assert readiness.status == "incomplete"
    assert readiness.completed_required_count == 0
    assert [item.key for item in readiness.items] == [
        "storage",
        "network_access",
        "cloud_backup",
        "alerts",
        "schedule",
    ]
    assert {item.key: item.status for item in readiness.items} == {
        "storage": "incomplete",
        "network_access": "incomplete",
        "cloud_backup": "incomplete",
        "alerts": "incomplete",
        "schedule": "incomplete",
    }
    assert config.load_calls == 1


def test_backup_readiness_distinguishes_skipped_cloud_backup(tmp_path):
    config_data = _base_config()
    config_data["backup"]["cloud_skipped"] = "true"
    config = FakeConfigManager(config_data)

    readiness = build_backup_readiness(
        config,
        runtime=_runtime(tmp_path),
        smb_manager=FakeSmbManager([]),
    )

    cloud_item = next(item for item in readiness.items if item.key == "cloud_backup")
    assert cloud_item.status == "skipped"
    assert cloud_item.status_label == "Skipped"
    assert not cloud_item.complete
    assert readiness.status == "incomplete"


def test_backup_readiness_reports_complete_protection(tmp_path):
    config_data = _base_config()
    config_data["backup"].update(
        {
            "email_address": "admin@example.com",
            "from_address": "sss@example.com",
            "cloud_enabled": "true",
            "rclone_dir": "mega:/Backups",
        }
    )
    config_data["storage"]["storage_id"] = "storage-id"
    config_data["schedule"]["configured"] = "true"
    smtp_path = tmp_path / "smtp.conf"
    smtp_path.write_text(
        "\n".join(
            [
                "host smtp.example.com",
                "port 587",
                "from sss@example.com",
                "user admin@example.com",
                "password secret",
            ]
        ),
        encoding="utf-8",
    )

    readiness = build_backup_readiness(
        FakeConfigManager(config_data),
        runtime=_runtime(tmp_path),
        smb_manager=FakeSmbManager(
            [{"name": "backup", "path": "/srv/backups", "managed": True}]
        ),
    )

    assert readiness.status == "complete"
    assert readiness.complete
    assert readiness.completed_required_count == readiness.required_count == 5
    assert readiness.count_label == "5 of 5 complete"
    assert all(item.complete for item in readiness.items)


def test_backup_readiness_does_not_count_default_schedule_as_chosen(tmp_path):
    config_data = _base_config()
    config_data["storage"]["storage_id"] = "storage-id"

    readiness = build_backup_readiness(
        FakeConfigManager(config_data),
        runtime=_runtime(tmp_path),
        smb_manager=FakeSmbManager(
            [{"name": "backup", "path": "/srv/backups", "managed": True}]
        ),
    )

    schedule_item = next(item for item in readiness.items if item.key == "schedule")
    assert schedule_item.status == "incomplete"
    assert "Choose when" in schedule_item.detail
