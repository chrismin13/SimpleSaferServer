import unittest
from unittest.mock import patch

from simple_safer_server.adapters.command_runner import DEVNULL, CommandRunner


class CommandRunnerTests(unittest.TestCase):
    # CommandRunner.run must omit stdout/stderr so subprocess.run honors capture_output=True.
    def test_run_omits_unset_stdout_and_stderr_with_capture_output(self):
        runner = CommandRunner()

        with patch("subprocess.run") as subprocess_run:
            runner.run(["systemctl", "show", "example.service"], capture_output=True, text=True)

        subprocess_run.assert_called_once_with(
            ["systemctl", "show", "example.service"],
            capture_output=True,
            check=False,
            text=True,
        )

    # Explicit stdout/stderr and check/text overrides must reach the subprocess.run call unchanged.
    def test_run_keeps_explicit_stdout_and_stderr_overrides(self):
        runner = CommandRunner()

        with patch("subprocess.run") as subprocess_run:
            runner.run(
                ["systemctl", "start", "example.service", "--no-block"],
                stdout=DEVNULL,
                stderr=DEVNULL,
                check=True,
            )

        subprocess_run.assert_called_once_with(
            ["systemctl", "start", "example.service", "--no-block"],
            capture_output=False,
            check=True,
            text=False,
            stdout=DEVNULL,
            stderr=DEVNULL,
        )


if __name__ == "__main__":
    unittest.main()
