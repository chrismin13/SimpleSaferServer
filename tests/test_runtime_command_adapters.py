import unittest
from pathlib import Path
from types import SimpleNamespace

from simple_safer_server.adapters.command_runner import CommandRunner
from simple_safer_server.adapters.storage_commands import StorageCommandAdapter
from simple_safer_server.adapters.system_updates_commands import SystemUpdatesCommandAdapter
from simple_safer_server.adapters.user_commands import UserCommandAdapter


class RecordingRunner(CommandRunner):
    def __init__(self):
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")


class RuntimeCommandAdapterTests(unittest.TestCase):
    def test_storage_adapter_uses_root_direct_commands(self):
        runner = RecordingRunner()
        adapter = StorageCommandAdapter(command_runner=runner)

        adapter.reboot()
        adapter.poweroff()
        adapter.mount("/dev/sdb1", "/media/backup")
        adapter.mount_managed("/media/backup")
        adapter.start_unit("smbd")

        self.assertEqual(
            [call[0] for call in runner.calls],
            [
                ["systemctl", "reboot"],
                ["systemctl", "poweroff"],
                ["mount", "/dev/sdb1", "/media/backup"],
                ["mount", "/media/backup"],
                ["systemctl", "start", "smbd"],
            ],
        )

    def test_user_adapter_uses_root_direct_commands(self):
        runner = RecordingRunner()
        adapter = UserCommandAdapter(command_runner=runner)

        adapter.create_system_user("operator")
        adapter.samba_users()
        adapter.set_samba_password("operator", "secret")
        adapter.remove_samba_user("operator")
        adapter.remove_system_user("operator")

        self.assertEqual(
            [call[0] for call in runner.calls],
            [
                [
                    "useradd",
                    "--system",
                    "--no-create-home",
                    "--shell",
                    "/usr/sbin/nologin",
                    "operator",
                ],
                ["pdbedit", "-L"],
                ["smbpasswd", "-s", "-a", "operator"],
                ["smbpasswd", "-x", "operator"],
                ["userdel", "operator"],
            ],
        )

    def test_system_updates_adapter_uses_root_direct_commands(self):
        runner = RecordingRunner()
        adapter = SystemUpdatesCommandAdapter(command_runner=runner)

        adapter.is_lock_held("/usr/bin/fuser", Path("/var/lib/dpkg/lock"))
        adapter.livepatch_status_json("/usr/bin/canonical-livepatch")
        adapter.livepatch_status_text("/usr/bin/canonical-livepatch")

        self.assertEqual(
            [call[0] for call in runner.calls],
            [
                ["/usr/bin/fuser", "/var/lib/dpkg/lock"],
                ["/usr/bin/canonical-livepatch", "status", "--format", "json"],
                ["/usr/bin/canonical-livepatch", "status"],
            ],
        )


if __name__ == "__main__":
    unittest.main()
