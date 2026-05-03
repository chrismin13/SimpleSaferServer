from pathlib import Path
from typing import Optional

from simple_safer_server.adapters.command_runner import CommandRunner

SMB_COMMAND_TIMEOUT_SECONDS = 30


class SmbCommandAdapter:
    """Wraps Samba validation, backup, service, and status commands."""

    def __init__(self, command_runner: Optional[CommandRunner] = None) -> None:
        self._command_runner = command_runner or CommandRunner()

    def _command(self, *parts: str):
        return list(parts)

    def copy_config(self, source: str, backup_path: str) -> None:
        self._command_runner.run(
            self._command("cp", source, backup_path),
            check=True,
            timeout=SMB_COMMAND_TIMEOUT_SECONDS,
        )

    def validate_config(self, validator: str, candidate_path: Path):
        if Path(validator).name == "testparm":
            command = self._command(validator, "-s", str(candidate_path))
        else:
            command = self._command(validator, "-t", "-s", str(candidate_path))
        return self._command_runner.run(
            command,
            capture_output=True,
            text=True,
            timeout=SMB_COMMAND_TIMEOUT_SECONDS,
        )

    def restart_unit(self, unit_name: str) -> None:
        self._command_runner.run(
            self._command("systemctl", "restart", unit_name),
            check=True,
            timeout=SMB_COMMAND_TIMEOUT_SECONDS,
        )

    def unit_status(self, unit_name: str) -> str:
        result = self._command_runner.run(
            self._command("systemctl", "is-active", unit_name),
            capture_output=True,
            text=True,
            timeout=SMB_COMMAND_TIMEOUT_SECONDS,
        )
        return result.stdout.strip()
