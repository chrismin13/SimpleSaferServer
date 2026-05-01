import logging
import types
import unittest
from pathlib import Path
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory

from simple_safer_server.services.cloud_backup_service import CloudBackupService


class FakeConfigManager:
    def __init__(self):
        self.config = {"backup": {}, "schedule": {}}

    def get_all_config(self):
        return self.config

    def get_value(self, section, key, default=None):
        return self.config.get(section, {}).get(key, default)

    def set_value(self, section, key, value):
        self.config.setdefault(section, {})[key] = value


class FakeSystemUtils:
    def __init__(self):
        self.rclone_config = None
        self.created_systemd_config = False
        self.installed_timers = False

    def setup_rclone(self, config):
        self.rclone_config = config
        return True

    def create_systemd_config_file(self, config):
        self.created_systemd_config = True
        return True, None

    def install_systemd_services_and_timers(self, config):
        self.installed_timers = True
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


class FakeCommandRunner:
    def __init__(self):
        self.calls = []
        self.results = []

    def queue_result(self, returncode=0, stdout="", stderr=""):
        self.results.append(
            types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
        )

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if not self.results:
            raise AssertionError("No fake command result queued.")
        result = self.results.pop(0)
        if kwargs.get("check") and result.returncode != 0:
            raise CalledProcessError(
                result.returncode, command, output=result.stdout, stderr=result.stderr
            )
        return result


class CloudBackupServiceTests(unittest.TestCase):
    def make_service(self, is_fake=True, task=None, command_runner=None):
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
            logging.getLogger("test"),
            command_runner=command_runner,
        )
        return service, config, system_utils, runtime

    def test_get_config_exposes_existing_rclone_text_for_admin_editing(self):
        service, config, _system_utils, runtime = self.make_service()
        config.config["backup"] = {
            "cloud_mode": "advanced",
            "mega_email": "user@example.com",
            "mega_pass": "secret",
            "rclone_dir": "remote:/backups",
        }
        config.config["schedule"] = {"backup_cloud_time": "02:30"}
        rclone_path = runtime.rclone_config_dir / "rclone.conf"
        rclone_path.write_text("[remote]\ntype = test\n")

        payload = service.get_config()

        self.assertEqual(payload["mega_email"], "user@example.com")
        self.assertNotIn("mega_pass", payload)
        self.assertEqual(payload["rclone_config"], "[remote]\ntype = test\n")

    def test_status_and_manual_run_use_cloud_backup_task(self):
        task = FakeTask()
        service, _config, _system_utils, _runtime = self.make_service(task=task)

        self.assertEqual(service.get_status()["status"]["next_run"], "tomorrow")
        self.assertEqual(service.run_backup(), {"success": True})
        self.assertEqual(task.starts, 1)

    def test_fake_schedule_save_does_not_reinstall_timers(self):
        service, config, system_utils, _runtime = self.make_service(is_fake=True)

        result = service.save_schedule({"backup_cloud_time": "04:00", "bandwidth_limit": "4M"})

        self.assertEqual(result, {"success": True})
        self.assertEqual(config.config["schedule"]["backup_cloud_time"], "04:00")
        self.assertEqual(config.config["backup"]["bandwidth_limit"], "4M")
        self.assertFalse(system_utils.created_systemd_config)
        self.assertFalse(system_utils.installed_timers)

    def test_advanced_config_requires_remote_and_rclone_config(self):
        service, _config, _system_utils, _runtime = self.make_service()

        self.assertEqual(
            service.save_config({"cloud_mode": "advanced", "rclone_config": "", "remote_name": ""}),
            {"success": False, "error": "Rclone config and remote name are required."},
        )

    def test_mega_config_rewrites_rclone_when_reusing_stored_credentials(self):
        service, config, system_utils, _runtime = self.make_service()
        config.config["backup"] = {
            "mega_email": "user@example.com",
            "mega_pass": "stored-obscured",
        }

        result = service.save_config(
            {
                "cloud_mode": "mega",
                "mega_email": "user@example.com",
                "mega_folder": "/Backups",
            }
        )

        self.assertEqual(result, {"success": True})
        rclone_config = system_utils.rclone_config
        if rclone_config is None:
            self.fail("Expected rclone config to be written")
        self.assertIn("stored-obscured", rclone_config)

    def test_list_mega_folders_uses_command_runner(self):
        command_runner = FakeCommandRunner()
        command_runner.queue_result(stdout='[{"Name": "Backups", "IsDir": true}]')
        service, config, _system_utils, _runtime = self.make_service(command_runner=command_runner)
        config.config["backup"] = {"mega_email": "user@example.com", "mega_pass": "obscured"}

        result = service.list_mega_folders({"path": "/"})

        self.assertEqual(result["folders"], ["Backups"])
        self.assertEqual(command_runner.calls[0][0][:3], ["rclone", "lsjson", "mega:/"])
        self.assertTrue(command_runner.calls[0][1]["capture_output"])

    def test_validate_mega_uses_command_runner_for_obscure_and_lsjson(self):
        command_runner = FakeCommandRunner()
        command_runner.queue_result(stdout="obscured-password\n")
        command_runner.queue_result(stdout="[]")
        service, config, system_utils, _runtime = self.make_service(command_runner=command_runner)

        result = service.validate_mega({"email": "user@example.com", "password": "secret"})

        self.assertEqual(result, {"success": True})
        self.assertEqual(command_runner.calls[0][0], ["rclone", "obscure", "-"])
        self.assertEqual(command_runner.calls[0][1]["input"], "secret\n")
        self.assertEqual(command_runner.calls[1][0][0:3], ["rclone", "lsjson", "mega:/"])
        self.assertEqual(config.config["backup"]["mega_pass"], "obscured-password")
        rclone_config = system_utils.rclone_config
        self.assertIsNotNone(rclone_config)
        if rclone_config is not None:
            self.assertIn("obscured-password", rclone_config)


if __name__ == "__main__":
    unittest.main()
