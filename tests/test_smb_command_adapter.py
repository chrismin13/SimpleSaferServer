import unittest

from simple_safer_server.adapters.command_runner import CommandRunner
from simple_safer_server.adapters.smb_commands import SmbCommandAdapter


class RecordingRunner(CommandRunner):
    def __init__(self):
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))


class SmbCommandAdapterTests(unittest.TestCase):
    def test_copy_config_defaults_to_no_sudo(self):
        runner = RecordingRunner()
        adapter = SmbCommandAdapter(command_runner=runner)

        adapter.copy_config("/etc/samba/smb.conf", "/tmp/smb.conf.backup")

        self.assertEqual(
            runner.calls,
            [(["cp", "/etc/samba/smb.conf", "/tmp/smb.conf.backup"], {"check": True})],
        )

    def test_restart_unit_uses_root_direct_command(self):
        runner = RecordingRunner()
        adapter = SmbCommandAdapter(command_runner=runner)

        adapter.restart_unit("smbd")

        self.assertEqual(
            runner.calls,
            [(["systemctl", "restart", "smbd"], {"check": True})],
        )


if __name__ == "__main__":
    unittest.main()
