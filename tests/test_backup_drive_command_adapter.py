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

    def test_mount_ntfs_defaults_to_ntfs_3g_binary(self):
        runner = FakeCommandRunner()
        adapter = BackupDriveCommandAdapter(command_runner=cast(Any, runner))

        adapter.mount_ntfs("/dev/sdb1", "/media/backup")

        self.assertEqual(runner.calls[0][0][0:3], ["ntfs-3g", "/dev/sdb1", "/media/backup"])
        self.assertEqual(runner.calls[0][0][3], "-o")
        self.assertIn("rw,uid=", runner.calls[0][0][4])

    def test_mount_ntfs3_uses_kernel_mount_type(self):
        runner = FakeCommandRunner()
        adapter = BackupDriveCommandAdapter(command_runner=cast(Any, runner))

        adapter.mount_ntfs("/dev/sdb1", "/media/backup", ntfs_driver="ntfs3")

        self.assertEqual(
            runner.calls[0][0][0:5], ["mount", "-t", "ntfs3", "/dev/sdb1", "/media/backup"]
        )
        self.assertEqual(runner.calls[0][0][5], "-o")
        self.assertEqual(runner.calls[0][0][6], "rw,uid=0,gid=0,dmask=000,fmask=000")


if __name__ == "__main__":
    unittest.main()
