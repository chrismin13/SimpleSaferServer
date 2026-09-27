import configparser
import copy
import threading
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from simple_safer_server.services.cloud_backup_service import (
    CloudBackupService,
)
from simple_safer_server.services.config_manager import ConfigManager, ConfigUpdate
from simple_safer_server.web.problems import OperationProblem, ValidationProblem


class FakeConfigManager:
    def __init__(self):
        self.config = {"backup": {}, "schedule": {}, "system": {"setup_complete": "true"}}

    def get_all_config(self):
        return copy.deepcopy(self.config)

    def get_value(self, section, key, default=None):
        return self.config.get(section, {}).get(key, default)

    def load_config(self):
        pass

    def update_values(self, values):
        previous = self.get_all_config()
        for section, entries in values.items():
            self.config.setdefault(section, {}).update(entries)
        return ConfigUpdate(previous, self.get_all_config())

    def set_value(self, section, key, value):
        self.config.setdefault(section, {})[key] = value


class FakeSystemUtils:
    def __init__(self):
        self.created_systemd_config = False
        self.installed_timers = False
        self.activated_timers = False
        self.systemd_config = None

    def create_systemd_config_file(self, config):
        self.created_systemd_config = True
        self.systemd_config = config
        return True, None

    def install_systemd_services_and_timers(self, config, activate_timers=True):
        self.systemd_config = config
        self.installed_timers = True
        self.activated_timers = activate_timers
        return True, None


class FakeTask:
    def __init__(self):
        self.status = "Success"
        self.last_run = "yesterday"
        self.next_run = "tomorrow"
        self.last_run_duration = "1m"
        self.starts = 0

    def start(self):
        self.starts += 1


class FakeTaskService:
    def __init__(self, task=None):
        self.task = task

    def get_task(self, name):
        if name == "Cloud Backup":
            return self.task
        return None


class CloudBackupServiceTests(unittest.TestCase):
    def make_service(self, is_fake=True, task=None):
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        runtime = types.SimpleNamespace(
            is_fake=is_fake,
            rclone_config_dir=Path(temp_dir.name),
        )
        config = FakeConfigManager()
        system_utils = FakeSystemUtils()
        task_service = FakeTaskService(task=task)
        service = CloudBackupService(
            runtime,
            config,
            system_utils,
            task_service,
        )
        return service, config, system_utils, runtime

    def test_public_settings_keep_credentials_in_dedicated_editor(self):
        service, config, _utils, runtime = self.make_service()
        config.config["backup"] = {
            "cloud_enabled": "true",
            "mega_pass": "secret",
            "rclone_dir": "remote:backups",
        }
        (runtime.rclone_config_dir / "rclone.conf").write_text("[remote]\ntype = local\n")
        payload = service.get_config()
        self.assertNotIn("rclone_config", payload)
        self.assertNotIn("mega_pass", payload)
        self.assertEqual(payload["rclone_dir"], "remote:backups")

    def test_destination_save_defers_timers_until_setup_complete(self):
        service, config, system_utils, _runtime = self.make_service(is_fake=False)
        config.config["system"] = {"setup_complete": "false"}
        service.save_destination("remote:backups", True)
        self.assertEqual(config.config["backup"]["cloud_enabled"], "true")
        self.assertFalse(system_utils.installed_timers)
        self.assertFalse(system_utils.activated_timers)
        config.config["system"]["setup_complete"] = "true"
        service.save_destination("remote:backups", True)
        self.assertTrue(system_utils.activated_timers)

    def test_failed_timer_update_restores_destination_and_enabled(self):
        service, config, system_utils, _runtime = self.make_service(is_fake=False)
        config.config["backup"] = {"cloud_enabled": "false", "rclone_dir": "saved:folder"}
        system_utils.install_systemd_services_and_timers = lambda *a, **kw: (False, "Unavailable")
        with self.assertRaises(OperationProblem):
            service.save_destination("new:folder", True)
        self.assertEqual(
            config.config["backup"], {"cloud_enabled": "false", "rclone_dir": "saved:folder"}
        )

    def test_status_and_manual_run_use_cloud_backup_task(self):
        task = FakeTask()
        service, config, _system_utils, _runtime = self.make_service(task=task)
        config.config["backup"]["cloud_enabled"] = "true"

        self.assertEqual(service.get_status().next_run, "tomorrow")
        self.assertIsNone(service.run_backup())
        self.assertEqual(task.starts, 1)

    def test_status_fails_when_cloud_enabled_is_missing(self):
        task = FakeTask()
        service, _config, _system_utils, _runtime = self.make_service(task=task)

        with self.assertRaisesRegex(ValidationProblem, "missing or invalid"):
            service.get_status()

    def test_manual_run_fails_when_cloud_enabled_is_invalid(self):
        task = FakeTask()
        service, config, _system_utils, _runtime = self.make_service(task=task)
        config.config["backup"]["cloud_enabled"] = "maybe"

        with self.assertRaisesRegex(ValidationProblem, "missing or invalid"):
            service.run_backup()

    def test_disabled_cloud_backup_status_does_not_start_task(self):
        task = FakeTask()
        service, config, _system_utils, _runtime = self.make_service(task=task)
        config.config["backup"]["cloud_enabled"] = "false"

        status = service.get_status()

        self.assertEqual(status.status, "Disabled")
        with self.assertRaisesRegex(ValidationProblem, "disabled"):
            service.run_backup()
        self.assertEqual(task.starts, 0)

    def test_save_config_accepts_string_false_for_cloud_enabled(self):
        service, config, _system_utils, _runtime = self.make_service()

        service.save_destination("", False)

        self.assertEqual(config.config["backup"]["cloud_enabled"], "false")

    def test_real_save_config_refreshes_timers_when_cloud_backup_is_disabled(self):
        service, config, system_utils, _runtime = self.make_service(is_fake=False)

        service.save_destination("", False)

        self.assertEqual(config.config["backup"]["cloud_enabled"], "false")
        self.assertTrue(system_utils.installed_timers)

    def test_fake_schedule_save_does_not_reinstall_timers(self):
        service, config, system_utils, _runtime = self.make_service(is_fake=True)

        result = service.save_schedule({"backup_cloud_time": "04:00", "bandwidth_limit": "4M"})

        self.assertEqual(result, {})
        self.assertEqual(config.config["schedule"]["backup_cloud_time"], "04:00")
        self.assertEqual(config.config["backup"]["bandwidth_limit"], "4M")
        self.assertFalse(system_utils.created_systemd_config)
        self.assertFalse(system_utils.installed_timers)

    def test_schedule_save_rejects_unsafe_bandwidth_limit(self):
        service, config, _system_utils, _runtime = self.make_service(is_fake=True)

        with self.assertRaisesRegex(ValidationProblem, "Bandwidth limit"):
            service.save_schedule(
                {"backup_cloud_time": "04:00", "bandwidth_limit": "4M --delete-excluded"}
            )

        self.assertNotIn("bandwidth_limit", config.config["backup"])

    def test_fake_schedule_save_rejects_non_strict_time(self):
        service, config, system_utils, _runtime = self.make_service(is_fake=True)

        with self.assertRaisesRegex(ValidationProblem, "HH:MM"):
            service.save_schedule({"backup_cloud_time": "4:00", "bandwidth_limit": "4M"})

        self.assertNotIn("backup_cloud_time", config.config["schedule"])
        self.assertNotIn("bandwidth_limit", config.config["backup"])
        self.assertFalse(system_utils.created_systemd_config)

    def test_real_config_save_routes_schedule_values_through_timer_update(self):
        service, config, system_utils, _runtime = self.make_service(is_fake=False)

        result = service.save_schedule(
            {
                "cloud_mode": "",
                "backup_cloud_time": "05:15",
                "bandwidth_limit": "8M",
            }
        )

        self.assertEqual(result, {})
        self.assertTrue(system_utils.installed_timers)
        systemd_config = system_utils.systemd_config
        if systemd_config is None:
            self.fail("Expected systemd config to be generated.")
        self.assertEqual(systemd_config["schedule"]["backup_cloud_time"], "05:15")
        self.assertEqual(config.config["schedule"]["backup_cloud_time"], "05:15")
        self.assertEqual(config.config["backup"]["bandwidth_limit"], "8M")

    def test_schedule_save_allows_bandwidth_only_update(self):
        service, config, system_utils, _runtime = self.make_service(is_fake=False)
        config.config["schedule"] = {"backup_cloud_time": "03:00"}

        result = service.save_schedule({"bandwidth_limit": "8M"})

        self.assertEqual(result, {})
        self.assertTrue(system_utils.installed_timers)
        self.assertEqual(config.config["schedule"]["backup_cloud_time"], "03:00")
        self.assertEqual(config.config["backup"]["bandwidth_limit"], "8M")


@pytest.mark.parametrize("operation", ["destination", "schedule"])
@pytest.mark.parametrize("timer_success", [True, False])
def test_save_uses_transaction_snapshots_during_status_reload(
    tmp_path, monkeypatch, operation, timer_success
):
    runtime = types.SimpleNamespace(
        is_fake=False, config_dir=tmp_path / "config", default_mount_point="/media/backup"
    )
    config = ConfigManager(runtime=runtime)
    config.update_values(
        {
            "system": {"setup_complete": "true"},
            "backup": {"cloud_enabled": "false", "rclone_dir": "initial:folder"},
            "schedule": {"backup_cloud_time": "03:00"},
        }
    )
    other_config = ConfigManager(runtime=runtime)
    system_utils = FakeSystemUtils()
    install_timers = system_utils.install_systemd_services_and_timers

    def install(config, **kwargs):
        install_timers(config, **kwargs)
        return timer_success, None if timer_success else "Unavailable"

    monkeypatch.setattr(system_utils, "install_systemd_services_and_timers", install)
    service = CloudBackupService(runtime, config, system_utils, FakeTaskService())
    read_finished = threading.Event()
    resume_reload = threading.Event()
    original_read = configparser.ConfigParser.read
    statuses = []

    def delayed_read(parser, *args, **kwargs):
        result = original_read(parser, *args, **kwargs)
        if threading.current_thread() is reader:
            # Hold a real status request just before load_config replaces the
            # shared parser, then let it publish its stale read after the save.
            read_finished.set()
            assert resume_reload.wait(5)
        return result

    reader = threading.Thread(target=lambda: statuses.append(service.get_status()))
    monkeypatch.setattr(configparser.ConfigParser, "read", delayed_read)
    original_update = config.update_values
    first_update = True
    previous = config.get_all_config()

    def update(values):
        nonlocal first_update, previous
        if not first_update:
            return original_update(values)
        first_update = False
        if not timer_success:
            # Rollback must restore the file the transaction actually read,
            # including another writer's update before it acquired the lock.
            other_config.update_values(
                {
                    "backup": {"rclone_dir": "saved:folder", "cloud_enabled": "true"},
                    "schedule": {"backup_cloud_time": "04:00"},
                    "system": {"server_name": "other-writer"},
                }
            )
            previous = other_config.get_all_config()
        result = original_update(values)
        resume_reload.set()
        reader.join(5)
        assert not reader.is_alive()
        return result

    monkeypatch.setattr(config, "update_values", update)
    changes = (
        {"backup": {"rclone_dir": "new:folder", "cloud_enabled": "true"}}
        if operation == "destination"
        else {"backup": {"bandwidth_limit": "8M"}, "schedule": {"backup_cloud_time": "05:15"}}
    )

    def save():
        if operation == "destination":
            service.save_destination("new:folder", True)
        else:
            service.save_schedule({"backup_cloud_time": "05:15", "bandwidth_limit": "8M"})

    reader.start()
    try:
        assert read_finished.wait(5)
        if timer_success:
            save()
        else:
            with pytest.raises(OperationProblem, match="Unavailable"):
                save()
    finally:
        resume_reload.set()
        reader.join(5)
    assert not reader.is_alive()
    assert len(statuses) == 1
    assert statuses[0].status == "Disabled"

    published = copy.deepcopy(previous)
    for section, values in changes.items():
        published[section].update(values)
    assert system_utils.systemd_config == published
    config.load_config()
    assert config.get_all_config() == (published if timer_success else previous)


if __name__ == "__main__":
    unittest.main()
