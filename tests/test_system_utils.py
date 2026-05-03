import configparser
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


class SystemUtilsTimerActivationTests(unittest.TestCase):
    def _runtime(self, temp_dir):
        return types.SimpleNamespace(
            is_fake=False,
            systemd_dir=Path(temp_dir) / "systemd",
        )

    def _config(self):
        return {
            "system": {"setup_complete": "false"},
            "schedule": {"backup_cloud_time": "03:00"},
        }

    def test_install_systemd_services_can_refresh_units_without_starting_timers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = self._runtime(temp_dir)
            runtime.systemd_dir.mkdir()
            system_utils = RecordingSystemUtils(runtime)

            ok, error = system_utils.install_systemd_services_and_timers(
                self._config(),
                activate_timers=False,
            )

            self.assertTrue(ok, error)
            self.assertIsNone(error)
            self.assertTrue((runtime.systemd_dir / "backup_cloud.timer").exists())
            self.assertIn((["systemctl", "daemon-reload"], True), system_utils.commands)
            self.assertNotIn(
                (["systemctl", "start", "backup_cloud.timer"], True), system_utils.commands
            )

            # Fresh installs write the unit files early, but Persistent=true timers must not
            # replay missed work until the setup wizard has collected the real backup config.
            for service_name in ["check_mount", "check_health", "backup_cloud", "ddns_update"]:
                self.assertIn(
                    (["systemctl", "stop", f"{service_name}.timer"], False), system_utils.commands
                )
                self.assertIn(
                    (["systemctl", "disable", f"{service_name}.timer"], False),
                    system_utils.commands,
                )
                self.assertIn(
                    (["systemctl", "disable", f"{service_name}.service"], False),
                    system_utils.commands,
                )

    def test_install_systemd_services_starts_timers_when_activation_is_enabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = self._runtime(temp_dir)
            runtime.systemd_dir.mkdir()
            system_utils = RecordingSystemUtils(runtime)

            ok, error = system_utils.install_systemd_services_and_timers(
                self._config(),
                activate_timers=True,
            )

            self.assertTrue(ok, error)
            self.assertIsNone(error)

            for service_name in ["check_mount", "check_health", "backup_cloud", "ddns_update"]:
                self.assertIn(
                    (["systemctl", "enable", f"{service_name}.service"], True),
                    system_utils.commands,
                )
                self.assertIn(
                    (["systemctl", "enable", f"{service_name}.timer"], True), system_utils.commands
                )
                self.assertIn(
                    (["systemctl", "start", f"{service_name}.timer"], True), system_utils.commands
                )

    def test_parent_device_fallback_strips_standard_partition_suffix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            system_utils = ParentDeviceFallbackSystemUtils(self._runtime(temp_dir))

            self.assertEqual(system_utils.get_parent_device("/dev/sda1"), "/dev/sda")

    def test_parent_device_fallback_strips_nvme_partition_suffix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            system_utils = ParentDeviceFallbackSystemUtils(self._runtime(temp_dir))

            self.assertEqual(system_utils.get_parent_device("/dev/nvme0n1p1"), "/dev/nvme0n1")

    def test_pre_backup_timers_keep_two_minute_spacing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = self._runtime(temp_dir)
            runtime.systemd_dir.mkdir()
            system_utils = RecordingSystemUtils(runtime)

            ok, error = system_utils.install_systemd_services_and_timers(
                self._config(),
                activate_timers=False,
            )

            self.assertTrue(ok, error)
            self.assertIsNone(error)
            self.assertIn(
                "OnCalendar=*-*-* 02:56:00",
                (runtime.systemd_dir / "check_mount.timer").read_text(),
            )
            self.assertIn(
                "OnCalendar=*-*-* 02:58:00",
                (runtime.systemd_dir / "check_health.timer").read_text(),
            )
            self.assertIn(
                "OnCalendar=*-*-* 03:00:00",
                (runtime.systemd_dir / "backup_cloud.timer").read_text(),
            )

    def test_pre_backup_timers_wrap_before_midnight(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = self._runtime(temp_dir)
            runtime.systemd_dir.mkdir()
            system_utils = RecordingSystemUtils(runtime)
            config = self._config()
            config["schedule"]["backup_cloud_time"] = "00:01"

            ok, error = system_utils.install_systemd_services_and_timers(
                config,
                activate_timers=False,
            )

            self.assertTrue(ok, error)
            self.assertIsNone(error)
            self.assertIn(
                "OnCalendar=*-*-* 23:57:00",
                (runtime.systemd_dir / "check_mount.timer").read_text(),
            )
            self.assertIn(
                "OnCalendar=*-*-* 23:59:00",
                (runtime.systemd_dir / "check_health.timer").read_text(),
            )

    def test_install_systemd_services_normalizes_legacy_single_digit_hour(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = self._runtime(temp_dir)
            runtime.systemd_dir.mkdir()
            system_utils = RecordingSystemUtils(runtime)
            config = self._config()
            config["schedule"]["backup_cloud_time"] = "3:00"

            ok, error = system_utils.install_systemd_services_and_timers(
                config,
                activate_timers=False,
            )

            self.assertTrue(ok, error)
            self.assertIsNone(error)
            self.assertIn(
                "OnCalendar=*-*-* 03:00:00",
                (runtime.systemd_dir / "backup_cloud.timer").read_text(),
            )

    def test_install_systemd_services_rejects_invalid_backup_time_seconds(self):
        invalid_values = [
            "03:00:99",  # too many seconds
            "03:00:00:00",  # too many components
            "03",  # missing minutes
            "24:00",  # hour out of range
            "03:60",  # minute out of range
            "+03:00",  # leading sign
            "03: 00",  # whitespace in component
            "bad:00",  # non-numeric hour
        ]
        for value in invalid_values:
            with tempfile.TemporaryDirectory() as temp_dir:
                runtime = self._runtime(temp_dir)
                runtime.systemd_dir.mkdir()
                system_utils = RecordingSystemUtils(runtime)
                config = self._config()
                config["schedule"]["backup_cloud_time"] = value

                ok, error = system_utils.install_systemd_services_and_timers(
                    config,
                    activate_timers=False,
                )

                self.assertFalse(ok, value)
                if error is None:
                    self.fail("Expected validation error")
                self.assertIn("schedule.backup_cloud_time", error)

    def test_create_systemd_config_file_serializes_multiline_values_safely(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = types.SimpleNamespace(
                is_fake=False,
                config_dir=Path(temp_dir) / "config",
                default_mount_point="/media/backup",
            )
            system_utils = RecordingSystemUtils(runtime)

            ok, error = system_utils.create_systemd_config_file(
                {
                    "system": {
                        "username": "admin",
                        "server_name": "safe\n[ddns]\ncloudflare_enabled = true",
                        "setup_complete": "true",
                    },
                    "backup": {},
                    "schedule": {},
                    "hdsentinel": {},
                    "ddns": {"cloudflare_enabled": "false"},
                }
            )

            self.assertTrue(ok, error)
            parser = configparser.ConfigParser()
            parser.read(runtime.config_dir / "config.conf")
            self.assertEqual(
                parser.get("system", "server_name"),
                "safe\n[ddns]\ncloudflare_enabled = true",
            )
            self.assertEqual(parser.get("ddns", "cloudflare_enabled"), "false")

    def test_create_systemd_config_file_includes_script_email_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = types.SimpleNamespace(
                is_fake=False,
                config_dir=Path(temp_dir) / "config",
                default_mount_point="/media/backup",
            )
            system_utils = RecordingSystemUtils(runtime)

            ok, error = system_utils.create_systemd_config_file(
                {
                    "backup": {
                        "email_address": "admin@example.com",
                        "from_address": "server@example.com",
                    },
                    "system": {},
                    "schedule": {},
                    "hdsentinel": {},
                    "ddns": {},
                }
            )

            self.assertTrue(ok, error)
            parser = configparser.ConfigParser()
            parser.read(runtime.config_dir / "config.conf")
            self.assertEqual(parser.get("backup", "email_address"), "admin@example.com")
            self.assertEqual(parser.get("backup", "from_address"), "server@example.com")


if __name__ == "__main__":
    unittest.main()
