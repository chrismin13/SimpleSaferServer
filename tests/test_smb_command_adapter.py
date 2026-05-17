import unittest
from pathlib import Path
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
    def test_validate_config_passes_optional_working_directory(self):
        runner = RecordingRunner()
        adapter = SmbCommandAdapter(command_runner=runner)

        adapter.validate_config("testparm", Path("/tmp/candidate.conf"), cwd=Path("/etc/samba"))

        self.assertEqual(
            runner.calls,
            [
                (
                    ["testparm", "-s", "/tmp/candidate.conf"],
                    {
                        "capture_output": True,
                        "text": True,
                        "timeout": SMB_COMMAND_TIMEOUT_SECONDS,
                        "cwd": "/etc/samba",
                    },
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
