import unittest
from types import SimpleNamespace
from unittest.mock import patch

import drive_health


class DriveHealthSupportTests(unittest.TestCase):
    @patch("drive_health.subprocess.run")
    @patch("drive_health.shutil.which")
    def test_get_smartctl_json_support_rechecks_after_runtime_upgrade(self, mock_which, mock_run):
        # This guards the easy-to-forget case where operators install or
        # upgrade smartmontools without restarting the web process.
        mock_which.side_effect = [None, "/usr/sbin/smartctl"]
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="smartctl supports -j", stderr="")

        first_result = drive_health.get_smartctl_json_support()
        second_result = drive_health.get_smartctl_json_support()

        self.assertEqual(first_result, (False, "smartctl is not installed on this machine."))
        self.assertEqual(second_result, (True, None))
        self.assertEqual(mock_which.call_count, 2)
        mock_run.assert_called_once_with(["smartctl", "-h"], capture_output=True, text=True)
