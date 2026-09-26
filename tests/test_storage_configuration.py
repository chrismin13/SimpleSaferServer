from functools import partial
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from simple_safer_server.services.config_manager import ConfigManager
from simple_safer_server.services.storage_configuration import (
    StorageConfigurationError,
    change_existing_folder,
)
from simple_safer_server.services.storage_location import (
    StorageLocationError,
    configure_existing_folder,
    get_storage_location,
    marker_path,
    validate_storage_ready_for_backup,
)


@pytest.fixture
def storage_change(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.mkdir()
    new.mkdir()
    runtime = SimpleNamespace(
        is_fake=True,
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        logs_dir=tmp_path / "logs",
        volatile_dir=tmp_path / "run",
        repo_root=tmp_path / "repo",
        default_mount_point=str(old),
    )
    config = ConfigManager(runtime=runtime)
    config.set_value("system", "username", "admin")
    config.set_value("system", "setup_complete", "true")
    runner = MagicMock()
    runner.run.return_value = SimpleNamespace(returncode=0, stdout="")
    configure_existing_folder(config, str(old), runtime=runtime, command_runner=runner)
    system = MagicMock()
    system.create_systemd_config_file.return_value = (True, None)
    system.install_systemd_services_and_timers.return_value = (True, None)
    smb = MagicMock()
    smb.get_managed_share.return_value = {"path": str(old)}
    return SimpleNamespace(
        old=old,
        new=new,
        config=config,
        system=system,
        smb=smb,
        runtime=runtime,
        runner=runner,
        change=partial(
            change_existing_folder,
            config_manager=config,
            smb_manager=smb,
            system_utils=system,
            runtime=runtime,
            command_runner=runner,
        ),
    )


def assert_old_storage_works(env, previous):
    env.config.load_config()
    assert get_storage_location(env.config, runtime=env.runtime) == previous
    assert env.config.get_value("backup", "mount_point") == str(env.old)
    validate_storage_ready_for_backup(
        env.config, env.system, runtime=env.runtime, command_runner=env.runner
    )


@pytest.mark.parametrize("fail_share", [False, True])
def test_reselecting_current_folder_keeps_marker_unchanged(storage_change, fail_share):
    env = storage_change
    previous = get_storage_location(env.config, runtime=env.runtime)
    marker = marker_path(env.old)
    before = marker.read_bytes()
    metadata = marker.stat()
    if fail_share:
        env.smb.ensure_default_backup_share.side_effect = ValueError("Samba validation failed")
        with pytest.raises(StorageConfigurationError, match="Samba validation failed"):
            env.change(str(env.old))
    else:
        env.change(str(env.old))

    assert marker.read_bytes() == before
    assert marker.stat().st_ino == metadata.st_ino
    assert marker.stat().st_mode == metadata.st_mode
    assert_old_storage_works(env, previous)


@pytest.mark.parametrize("has_marker", [False, True])
def test_share_failure_restores_destination_marker(storage_change, has_marker):
    env = storage_change
    previous = get_storage_location(env.config, runtime=env.runtime)
    marker = marker_path(env.new)
    original = b'{"storage_id": "other-folder"}\r\n'
    if has_marker:
        marker.parent.mkdir()
        marker.write_bytes(original)
        marker.chmod(0o640)
    env.smb.ensure_default_backup_share.side_effect = ValueError("Samba validation failed")

    with pytest.raises(StorageConfigurationError, match="Samba validation failed"):
        env.change(str(env.new))

    if has_marker:
        assert marker.read_bytes() == original
        assert marker.stat().st_mode & 0o777 == 0o640
    else:
        assert not marker.parent.exists()
    assert_old_storage_works(env, previous)


@pytest.mark.parametrize("previous_share", [True, False])
def test_timer_failure_restores_share_marker_config_and_timers(storage_change, previous_share):
    env = storage_change
    previous = get_storage_location(env.config, runtime=env.runtime)
    # A manually selected share path may differ from the configured storage path.
    share_path = env.old / "shared"
    share_path.mkdir()
    env.smb.get_managed_share.return_value = {"path": str(share_path)} if previous_share else None
    env.system.install_systemd_services_and_timers.side_effect = [
        (False, "systemd failed"),
        (True, None),
    ]

    with pytest.raises(StorageConfigurationError, match="Previous storage settings were restored"):
        env.change(str(env.new))

    assert_old_storage_works(env, previous)
    assert not marker_path(env.new).exists()
    if previous_share:
        env.smb.update_managed_share_path.assert_called_once_with("backup", str(share_path))
    else:
        env.smb.delete_managed_share.assert_called_once_with("backup")
    restored_config = env.system.install_systemd_services_and_timers.call_args.args[0]
    assert restored_config["storage"]["path"] == str(env.old)


def test_partial_config_write_failure_restores_working_storage(storage_change, monkeypatch):
    env = storage_change
    previous = get_storage_location(env.config, runtime=env.runtime)
    original_set_value = env.config.set_value
    failed = False

    def fail_once(section, key, value):
        nonlocal failed
        if key == "storage_id" and not failed:
            failed = True
            raise OSError("config write failed")
        original_set_value(section, key, value)

    monkeypatch.setattr(env.config, "set_value", fail_once)

    with pytest.raises(StorageConfigurationError, match="config write failed"):
        env.change(str(env.new))

    assert_old_storage_works(env, previous)
    assert not marker_path(env.new).exists()
    env.smb.update_managed_share_path.assert_called_once_with("backup", str(env.old))


def test_timer_recovery_failure_is_reported(storage_change):
    env = storage_change
    env.system.install_systemd_services_and_timers.return_value = (False, "systemd unavailable")

    with pytest.raises(StorageConfigurationError, match="Recovery could not restore task timers"):
        env.change(str(env.new))


def test_mismatched_current_marker_requires_explicit_repair(storage_change):
    env = storage_change
    marker = marker_path(env.old)
    marker.write_text('{"storage_id": "wrong"}')

    with pytest.raises(StorageLocationError, match="repair its marker"):
        env.change(str(env.old))

    assert marker.read_text() == '{"storage_id": "wrong"}'
    env.smb.ensure_default_backup_share.assert_not_called()
