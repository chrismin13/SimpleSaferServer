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


class ConfigurableRunner(CommandRunner):
    """Runner that returns preconfigured results keyed by command prefix."""

    def __init__(self, results=None):
        self.calls = []
        self._results = results or {}

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        # Match on the first two args (e.g. ["systemctl", "is-active"])
        key = tuple(command[:2]) if len(command) >= 2 else tuple(command)
        if key in self._results:
            return self._results[key]
        return SimpleNamespace(returncode=0, stdout="", stderr="")


class UnitStatusTests(unittest.TestCase):
    def test_unit_status_returns_active_when_running(self):
        runner = ConfigurableRunner(
            results={
                ("systemctl", "is-active"): SimpleNamespace(
                    returncode=0, stdout="active\n", stderr=""
                ),
            }
        )
        adapter = SmbCommandAdapter(command_runner=runner)

        self.assertEqual(adapter.unit_status("smbd"), "active")

    def test_unit_status_returns_inactive_when_stopped_but_unit_exists(self):
        runner = ConfigurableRunner(
            results={
                ("systemctl", "is-active"): SimpleNamespace(
                    returncode=3, stdout="inactive\n", stderr=""
                ),
                ("systemctl", "cat"): SimpleNamespace(returncode=0, stdout="[Unit]\n", stderr=""),
            }
        )
        adapter = SmbCommandAdapter(command_runner=runner)

        self.assertEqual(adapter.unit_status("wsdd2"), "inactive")

    def test_unit_status_returns_unavailable_when_unit_file_missing(self):
        runner = ConfigurableRunner(
            results={
                ("systemctl", "is-active"): SimpleNamespace(
                    returncode=3, stdout="inactive\n", stderr=""
                ),
                ("systemctl", "cat"): SimpleNamespace(
                    returncode=1, stdout="", stderr="No files found\n"
                ),
            }
        )
        adapter = SmbCommandAdapter(command_runner=runner)

        self.assertEqual(adapter.unit_status("wsdd2"), "unavailable")


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

    def test_reload_config_uses_smbcontrol_command(self):
        runner = RecordingRunner()
        adapter = SmbCommandAdapter(command_runner=runner)

        adapter.reload_config()

        self.assertEqual(
            runner.calls,
            [
                (
                    ["smbcontrol", "smbd", "reload-config"],
                    {"check": True, "timeout": SMB_COMMAND_TIMEOUT_SECONDS},
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
