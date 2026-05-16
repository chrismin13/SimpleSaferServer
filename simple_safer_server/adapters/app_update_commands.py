from pathlib import Path
from typing import List, Optional

from simple_safer_server.adapters.command_runner import CommandRunner

APP_UPDATE_COMMAND_TIMEOUT_SECONDS = 300
APP_UPDATE_INSTALL_TIMEOUT_SECONDS = 1800


class AppUpdateCommandAdapter:
    """Runs Git and installer commands for application self-updates."""

    def __init__(self, command_runner: Optional[CommandRunner] = None) -> None:
        self._command_runner = command_runner or CommandRunner()

    def run_git(self, repo_path: Path, args: List[str], *, check: bool = False, timeout=None):
        return self._command_runner.run(
            ["git", *args],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=check,
            timeout=timeout or APP_UPDATE_COMMAND_TIMEOUT_SECONDS,
        )

    def run_git_for_journal(
        self, repo_path: Path, args: List[str], *, check: bool = False, timeout=None
    ):
        # app_update.service already sends stdout/stderr to journald. Letting
        # the child process inherit those streams keeps long installer output
        # visible on /task/App Update instead of buffering it in Python.
        return self._command_runner.run(
            ["git", *args],
            cwd=str(repo_path),
            check=check,
            timeout=timeout or APP_UPDATE_COMMAND_TIMEOUT_SECONDS,
        )

    def run_installer(self, repo_path: Path):
        # The installer owns service refresh and web restart behavior. Running it
        # from the pulled checkout keeps scheduled and manual updates identical.
        return self._command_runner.run(
            ["bash", "install.sh"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=False,
            timeout=APP_UPDATE_INSTALL_TIMEOUT_SECONDS,
        )

    def run_installer_for_journal(self, repo_path: Path):
        # The installer may restart the web service while this task is running;
        # journald is the durable progress surface across that restart.
        return self._command_runner.run(
            ["bash", "install.sh"],
            cwd=str(repo_path),
            check=False,
            timeout=APP_UPDATE_INSTALL_TIMEOUT_SECONDS,
        )
