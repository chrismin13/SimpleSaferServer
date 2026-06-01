import unittest
from types import SimpleNamespace
from typing import Any, cast

from simple_safer_server.adapters.backup_drive_commands import BackupDriveCommandAdapter


class FakeCommandRunner:
    def __init__(self, responses=None, default_response=None):
        self.calls = []
        self.responses = list(responses or [])
        self.default_response = default_response or SimpleNamespace(
            returncode=7, stdout="", stderr="busy"
        )

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if self.responses:
            return self.responses.pop(0)
        return self.default_response


class BackupDriveCommandAdapterTests(unittest.TestCase):
    def test_privileged_commands_run_without_sudo(self):
        runner = FakeCommandRunner()
        adapter = BackupDriveCommandAdapter(command_runner=cast(Any, runner))

        adapter.close_smb_share("/media/backup")
        adapter.stop_unit("smbd")
        adapter.start_unit("smbd")
        adapter.power_down_device("/dev/sdb")

        self.assertEqual(
            [call[0] for call in runner.calls],
            [
                ["smbcontrol", "all", "close-share", "/media/backup"],
                ["systemctl", "stop", "smbd"],
                ["systemctl", "start", "smbd"],
                ["hdparm", "-y", "/dev/sdb"],
            ],
        )

    def test_unmount_returns_nonzero_result_for_callers_to_handle(self):
        runner = FakeCommandRunner()
        adapter = BackupDriveCommandAdapter(command_runner=cast(Any, runner))

        result = adapter.unmount_partition("/dev/sdb1")

        self.assertEqual(result.returncode, 7)
        self.assertEqual(runner.calls[0][0], ["umount", "/dev/sdb1"])
        self.assertFalse(runner.calls[0][1]["check"])
        self.assertTrue(runner.calls[0][1]["capture_output"])

    def test_mount_ntfs3_uses_kernel_mount_type(self):
        runner = FakeCommandRunner(default_response=SimpleNamespace(returncode=0, stdout="", stderr=""))
        adapter = BackupDriveCommandAdapter(command_runner=cast(Any, runner))

        adapter.mount_ntfs("/dev/sdb1", "/media/backup", "ntfs3")

        command = runner.calls[0][0]
        self.assertEqual(command[:4], ["mount", "-t", "ntfs3", "-o"])
        self.assertEqual(command[-2:], ["/dev/sdb1", "/media/backup"])


if __name__ == "__main__":
    unittest.main()
