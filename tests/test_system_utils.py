import tempfile
import types
import unittest
from pathlib import Path

from system_utils import SystemUtils


class RecordingSystemUtils(SystemUtils):
    def __init__(self, runtime):
        super().__init__(runtime=runtime)
        self.commands = []

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
            self.assertNotIn((["systemctl", "start", "backup_cloud.timer"], True), system_utils.commands)

            # Fresh installs write the unit files early, but Persistent=true timers must not
            # replay missed work until the setup wizard has collected the real backup config.
            for service_name in ["check_mount", "check_health", "backup_cloud", "ddns_update"]:
                self.assertIn((["systemctl", "stop", f"{service_name}.timer"], False), system_utils.commands)
                self.assertIn((["systemctl", "disable", f"{service_name}.timer"], False), system_utils.commands)
                self.assertIn((["systemctl", "disable", f"{service_name}.service"], False), system_utils.commands)

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
                self.assertIn((["systemctl", "enable", f"{service_name}.service"], True), system_utils.commands)
                self.assertIn((["systemctl", "enable", f"{service_name}.timer"], True), system_utils.commands)
                self.assertIn((["systemctl", "start", f"{service_name}.timer"], True), system_utils.commands)
                self.assertNotIn((["systemctl", "disable", f"{service_name}.timer"], False), system_utils.commands)


if __name__ == "__main__":
    unittest.main()
