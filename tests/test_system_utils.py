import tempfile
import types
import unittest
from pathlib import Path

from simple_safer_server.services.system_utils import SystemUtils


class RecordingSystemUtils(SystemUtils):
    def __init__(self, runtime):
        super().__init__(runtime=runtime)
        self.commands = []

    def run_command(self, command, check=True):
        self.commands.append((command, check))
        return ""


class ParentDeviceFallbackSystemUtils(RecordingSystemUtils):
    def run_command(self, command, check=True):
        self.commands.append((command, check))
        return ""


class SystemUtilsTests(unittest.TestCase):
    def _runtime(self, temp_dir):
        return types.SimpleNamespace(
            is_fake=False,
            systemd_dir=Path(temp_dir) / "systemd",
            data_dir=Path(temp_dir) / "data",
            smtp_config_path=Path(temp_dir) / "config" / "smtp.conf",
        )

    def _config(self):
        return {
            "system": {"setup_complete": "false"},
            "backup": {"cloud_enabled": "true"},
            "storage": {"mode": "managed_drive"},
            "schedule": {"backup_cloud_time": "03:00"},
        }

    def test_worker_schedule_validation_does_not_write_feature_units(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = self._runtime(temp_dir)
            runtime.systemd_dir.mkdir()
            runtime.data_dir.mkdir()
            system_utils = RecordingSystemUtils(runtime)

            ok, error = system_utils.validate_worker_task_config(self._config())

            self.assertTrue(ok, error)
            self.assertIsNone(error)
            self.assertEqual(system_utils.commands, [])
            self.assertEqual(list(runtime.systemd_dir.iterdir()), [])

    def test_worker_schedule_validation_rejects_single_digit_hour(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = self._runtime(temp_dir)
            runtime.systemd_dir.mkdir()
            system_utils = RecordingSystemUtils(runtime)
            config = self._config()
            config["schedule"]["backup_cloud_time"] = "3:00"

            ok, error = system_utils.validate_worker_task_config(config)

            self.assertFalse(ok)
            self.assertIn("HH:MM", error)

    def test_worker_schedule_validation_rejects_invalid_backup_time(self):
        invalid_values = [
            "03:00:99",
            "03:00:00:00",
            "03",
            "24:00",
            "03:60",
            "+03:00",
            "03: 00",
            "bad:00",
        ]
        for value in invalid_values:
            with tempfile.TemporaryDirectory() as temp_dir:
                runtime = self._runtime(temp_dir)
                runtime.systemd_dir.mkdir()
                system_utils = RecordingSystemUtils(runtime)
                config = self._config()
                config["schedule"]["backup_cloud_time"] = value

                ok, error = system_utils.validate_worker_task_config(config)

                self.assertFalse(ok, value)
                if error is None:
                    self.fail("Expected validation error")
                self.assertIn("HH:MM", error)

    def test_parent_device_fallback_strips_standard_partition_suffix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            system_utils = ParentDeviceFallbackSystemUtils(self._runtime(temp_dir))

            self.assertEqual(system_utils.get_parent_device("/dev/sda1"), "/dev/sda")

    def test_parent_device_fallback_strips_nvme_partition_suffix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            system_utils = ParentDeviceFallbackSystemUtils(self._runtime(temp_dir))

            self.assertEqual(system_utils.get_parent_device("/dev/nvme0n1p1"), "/dev/nvme0n1")

if __name__ == "__main__":
    unittest.main()
