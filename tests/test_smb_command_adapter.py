import unittest
from types import SimpleNamespace

from simple_safer_server.adapters.command_runner import CommandRunner
from simple_safer_server.adapters.smb_commands import SMB_COMMAND_TIMEOUT_SECONDS, SmbCommandAdapter


class RecordingRunner(CommandRunner):
    def __init__(self):
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")


class SmbCommandAdapterTests(unittest.TestCase):
    def test_copy_config_defaults_to_no_sudo(self):
        runner = RecordingRunner()
        adapter = SmbCommandAdapter(command_runner=runner)

        adapter.copy_config("/etc/samba/smb.conf", "/tmp/smb.conf.backup")

        self.assertEqual(
            runner.calls,
            [
                (
                    ["cp", "/etc/samba/smb.conf", "/tmp/smb.conf.backup"],
                    {"check": True, "timeout": SMB_COMMAND_TIMEOUT_SECONDS},
                )
            ],
        )

    def test_restart_unit_uses_root_direct_command(self):
        runner = RecordingRunner()
        adapter = SmbCommandAdapter(command_runner=runner)

        adapter.restart_unit("smbd")

        self.assertEqual(
            runner.calls,
            [
                (
                    ["systemctl", "restart", "smbd"],
                    {"check": True, "timeout": SMB_COMMAND_TIMEOUT_SECONDS},
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
