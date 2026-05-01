from pathlib import Path
from typing import Optional

from simple_safer_server.adapters.command_runner import CommandRunner


class SmbCommandAdapter:
    """Wraps Samba validation, backup, service, and status commands."""

    def __init__(
        self, command_runner: Optional[CommandRunner] = None, use_sudo: bool = False
    ) -> None:
        self._command_runner = command_runner or CommandRunner()
        self._use_sudo = use_sudo

    def _command(self, *parts: str):
        # SimpleSaferServer normally runs as root; sudo stays opt-in for tests
        # or developer workflows that intentionally exercise non-root command paths.
        command = list(parts)
        if self._use_sudo:
            return ["sudo", *command]
        return command

    def copy_config(self, source: str, backup_path: str) -> None:
        self._command_runner.run(self._command("cp", source, backup_path), check=True)

    def validate_config(self, validator: str, candidate_path: Path):
        if Path(validator).name == "testparm":
            command = self._command(validator, "-s", str(candidate_path))
        else:
            command = self._command(validator, "-t", "-s", str(candidate_path))
        return self._command_runner.run(command, capture_output=True, text=True)

    def restart_unit(self, unit_name: str) -> None:
        self._command_runner.run(self._command("systemctl", "restart", unit_name), check=True)

    def unit_status(self, unit_name: str) -> str:
        result = self._command_runner.run(
            self._command("systemctl", "is-active", unit_name),
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
