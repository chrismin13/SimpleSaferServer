from types import SimpleNamespace

import pytest

from simple_safer_server.services.storage_location import (
    MODE_EXISTING_FOLDER,
    StorageLocationError,
    configure_existing_folder,
    get_storage_location,
    mark_prepared_drive_storage,
    marker_path,
    repair_storage_marker,
    validate_existing_folder_path,
    validate_storage_ready_for_backup,
)


class FakeConfigManager:
    def __init__(self, mount_point):
        self.config = {
            "backup": {"mount_point": str(mount_point), "uuid": "", "cloud_enabled": "false"},
            "storage": {},
        }

    def get_all_config(self):
        return self.config

    def get_value(self, section, key, default=None):
        return self.config.get(section, {}).get(key, default)

    def set_value(self, section, key, value):
        self.config.setdefault(section, {})[key] = str(value)


class FakeSystemUtils:
    def is_mounted(self, mount_point):
        return True


class FakeCommandRunner:
    def __init__(self, stdout="", command_outputs=None):
        self.stdout = stdout
        self.command_outputs = command_outputs or {}

    def run(self, command, **kwargs):
        key = tuple(command)
        if key in self.command_outputs:
            return SimpleNamespace(returncode=0, stdout=self.command_outputs[key], stderr="")
        return SimpleNamespace(returncode=0, stdout=self.stdout, stderr="")


def fake_runtime(tmp_path):
    return SimpleNamespace(
        config_dir=tmp_path / "etc",
        data_dir=tmp_path / "var-lib",
        logs_dir=tmp_path / "logs",
        volatile_dir=tmp_path / "run",
        repo_root=tmp_path / "repo",
        default_mount_point=str(tmp_path / "storage"),
        is_fake=True,
    )


def test_configure_existing_folder_writes_marker_and_config(tmp_path):
    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    runtime = fake_runtime(tmp_path)
    config = FakeConfigManager(storage_path)
    runner = FakeCommandRunner(f"/dev/sdb1 {storage_path} ext4\n")

    location = configure_existing_folder(
        config, str(storage_path), runtime=runtime, command_runner=runner
    )

    assert location.mode == MODE_EXISTING_FOLDER
    assert location.path == str(storage_path.resolve())
    assert marker_path(storage_path).exists()
    assert get_storage_location(config, runtime=runtime).storage_id


def test_storage_validation_fails_when_marker_is_missing(tmp_path):
    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    runtime = fake_runtime(tmp_path)
    config = FakeConfigManager(storage_path)
    configure_existing_folder(config, str(storage_path), runtime=runtime)
    marker_path(storage_path).unlink()

    with pytest.raises(StorageLocationError, match="Storage marker is missing"):
        validate_storage_ready_for_backup(config, FakeSystemUtils(), runtime=runtime)


def test_storage_validation_fails_when_marker_id_does_not_match(tmp_path):
    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    runtime = fake_runtime(tmp_path)
    config = FakeConfigManager(storage_path)
    configure_existing_folder(config, str(storage_path), runtime=runtime)
    marker_path(storage_path).write_text('{"storage_id": "wrong"}')

    with pytest.raises(StorageLocationError, match="does not match"):
        validate_storage_ready_for_backup(config, FakeSystemUtils(), runtime=runtime)


def test_storage_validation_fails_when_write_probe_readback_does_not_match(tmp_path, monkeypatch):
    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    runtime = fake_runtime(tmp_path)
    config = FakeConfigManager(storage_path)
    configure_existing_folder(config, str(storage_path), runtime=runtime)

    def write_wrong_value(path, _payload, mode=0o600):
        path.write_text("different")

    monkeypatch.setattr(
        "simple_safer_server.services.storage_location.atomic_write_text",
        write_wrong_value,
    )

    with pytest.raises(StorageLocationError, match="read back"):
        validate_storage_ready_for_backup(config, FakeSystemUtils(), runtime=runtime)


def test_repair_storage_marker_restores_missing_marker(tmp_path):
    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    runtime = fake_runtime(tmp_path)
    config = FakeConfigManager(storage_path)
    configure_existing_folder(config, str(storage_path), runtime=runtime)
    marker_path(storage_path).unlink()

    repair_storage_marker(config, runtime=runtime)

    assert validate_storage_ready_for_backup(config, FakeSystemUtils(), runtime=runtime)


def test_existing_folder_rejects_app_owned_paths(tmp_path):
    runtime = fake_runtime(tmp_path)
    runtime.config_dir.mkdir(parents=True)

    with pytest.raises(StorageLocationError, match="dedicated storage folder"):
        validate_existing_folder_path(str(runtime.config_dir), runtime=runtime)


def test_mount_identity_mismatch_fails_validation(tmp_path):
    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    runtime = fake_runtime(tmp_path)
    config = FakeConfigManager(storage_path)
    configure_existing_folder(
        config,
        str(storage_path),
        runtime=runtime,
        command_runner=FakeCommandRunner(f"/dev/sdb1 {storage_path} ext4\n"),
    )

    with pytest.raises(StorageLocationError, match="same mounted filesystem"):
        validate_storage_ready_for_backup(
            config,
            FakeSystemUtils(),
            runtime=runtime,
            command_runner=FakeCommandRunner(f"/dev/sdc1 {storage_path} ext4\n"),
        )


def test_prepared_drive_validation_requires_matching_mounted_uuid(tmp_path):
    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    runtime = fake_runtime(tmp_path)
    config = FakeConfigManager(storage_path)
    config.set_value("backup", "uuid", "EXPECTED-UUID")
    mark_prepared_drive_storage(config, str(storage_path), runtime=runtime)

    assert validate_storage_ready_for_backup(
        config,
        FakeSystemUtils(),
        runtime=runtime,
        command_runner=FakeCommandRunner("EXPECTED-UUID\n"),
    )


def test_prepared_drive_validation_fails_on_mounted_uuid_mismatch(tmp_path):
    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    runtime = fake_runtime(tmp_path)
    config = FakeConfigManager(storage_path)
    config.set_value("backup", "uuid", "EXPECTED-UUID")
    mark_prepared_drive_storage(config, str(storage_path), runtime=runtime)

    with pytest.raises(StorageLocationError, match="does not match"):
        validate_storage_ready_for_backup(
            config,
            FakeSystemUtils(),
            runtime=runtime,
            command_runner=FakeCommandRunner("OTHER-UUID\n"),
        )
