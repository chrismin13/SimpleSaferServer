import configparser
import tarfile
import types
from pathlib import Path

import pytest

from simple_safer_server.services.setup_self_backup import (
    BACKUP_ROOT_NAME,
    SetupSelfBackupError,
    SetupSelfBackupService,
)


class FakeConfigManager:
    def __init__(self, mount_point):
        self.mount_point = mount_point

    def get_value(self, section, key, default=None):
        if (section, key) == ("backup", "mount_point"):
            return str(self.mount_point)
        return default


def make_runtime(root: Path):
    return types.SimpleNamespace(
        is_fake=True,
        default_mount_point=str(root / "backup-drive"),
        config_dir=root / "config",
        data_dir=root / "data",
        rclone_config_dir=root / "rclone",
        samba_dir=root / "samba",
        msmtp_config_path=root / "msmtprc",
    )


def write_setup_files(runtime):
    runtime.config_dir.mkdir()
    runtime.data_dir.mkdir()
    runtime.rclone_config_dir.mkdir()
    runtime.samba_dir.mkdir()
    (runtime.config_dir / "config.conf").write_text(
        "[system]\nsetup_complete = true\n\n[backup]\nmount_point = /media/backup\n"
    )
    (runtime.config_dir / "users.json").write_text('{"admin": {}}\n')
    (runtime.config_dir / ".key").write_text("key")
    (runtime.config_dir / ".secrets").write_text("{}")
    (runtime.config_dir / ".flask-secret-key").write_text("flask-secret")
    (runtime.data_dir / "disabled_timers.json").write_text("{}")
    (runtime.rclone_config_dir / "rclone.conf").write_text("[remote]\ntype = test\n")
    runtime.msmtp_config_path.write_text("account default\n")
    (runtime.samba_dir / "simple_safer_server_shares.conf").write_text("[backup]\n")
    (runtime.config_dir / "backups").mkdir()
    (runtime.config_dir / "backups" / "fstab.20260101").write_text("do not include\n")


def test_create_backup_includes_only_setup_owned_whitelist(tmp_path):
    runtime = make_runtime(tmp_path)
    write_setup_files(runtime)
    service = SetupSelfBackupService(runtime, FakeConfigManager(tmp_path / "backup-drive"))

    result = service.create_backup()

    archive_path = Path(result["archive"])
    assert archive_path.parent == tmp_path / "backup-drive" / BACKUP_ROOT_NAME
    with tarfile.open(archive_path, "r:gz") as archive:
        names = set(archive.getnames())

    assert "manifest.json" in names
    assert "files/config/config.conf" in names
    assert "files/config/users.json" in names
    assert "files/rclone/rclone.conf" in names
    assert "files/msmtp/msmtprc" in names
    assert "files/samba/simple_safer_server_shares.conf" in names
    assert "files/config/backups/fstab.20260101" not in names
    assert not any("fstab" in name for name in names)


def test_restore_backup_forces_setup_incomplete(tmp_path):
    runtime = make_runtime(tmp_path)
    write_setup_files(runtime)
    service = SetupSelfBackupService(runtime, FakeConfigManager(tmp_path / "backup-drive"))
    archive_path = Path(service.create_backup()["archive"])

    (runtime.config_dir / "config.conf").write_text("[system]\nsetup_complete = true\n")
    (runtime.rclone_config_dir / "rclone.conf").write_text("[remote]\ntype = changed\n")

    result = service.restore_backup(archive_path)

    assert "config/config.conf" in result["restored"]
    assert "rclone/rclone.conf" in result["restored"]
    parser = configparser.ConfigParser()
    parser.read(runtime.config_dir / "config.conf")
    assert parser.get("system", "setup_complete") == "false"
    assert (runtime.rclone_config_dir / "rclone.conf").read_text() == "[remote]\ntype = test\n"


def test_create_backup_refuses_unmounted_real_destination(tmp_path):
    runtime = make_runtime(tmp_path)
    runtime.is_fake = False
    write_setup_files(runtime)
    service = SetupSelfBackupService(runtime, FakeConfigManager(tmp_path / "backup-drive"))

    with pytest.raises(SetupSelfBackupError, match="not a mounted backup drive"):
        service.create_backup()
