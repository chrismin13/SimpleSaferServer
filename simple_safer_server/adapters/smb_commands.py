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

    def validate_config(self, validator: str, candidate_path: Path, cwd: Optional[Path] = None):
        if Path(validator).name == "testparm":
            command = self._command(validator, "-s", str(candidate_path))
        else:
            command = self._command(validator, "-t", "-s", str(candidate_path))
        return self._command_runner.run(
            command,
            capture_output=True,
            text=True,
            timeout=SMB_COMMAND_TIMEOUT_SECONDS,
            cwd=str(cwd) if cwd is not None else None,
        )

    def restart_unit(self, unit_name: str) -> None:
        self._command_runner.run(
            self._command("systemctl", "restart", unit_name),
            check=True,
            timeout=SMB_COMMAND_TIMEOUT_SECONDS,
        )

    def reload_config(self) -> None:
        """Reload running smbd configuration gracefully using smbcontrol.

        This notifies active daemons via Samba's messaging interface to re-read
        their configuration files immediately, preventing active file transfers
        and TCP connections from dropping (unlike systemctl restart).
        """
        self._command_runner.run(
            self._command("smbcontrol", "smbd", "reload-config"),
            check=True,
            timeout=SMB_COMMAND_TIMEOUT_SECONDS,
        )

    def unit_status(self, unit_name: str) -> str:
        """Return 'active', 'inactive', or 'unavailable' for a systemd unit.

        'unavailable' means the unit file does not exist on this system (e.g.
        wsdd2 on distros that don't package it).  We distinguish this from
        'inactive' (unit exists but is stopped) by probing with systemctl cat.
        """
        result = self._command_runner.run(
            self._command("systemctl", "is-active", unit_name),
            capture_output=True,
            text=True,
            timeout=SMB_COMMAND_TIMEOUT_SECONDS,
        )
        status = result.stdout.strip()
        if status == "active":
            return "active"
        # 'inactive' from is-active covers both stopped units and missing units.
        # Check whether the unit file actually exists on disk.
        cat_result = self._command_runner.run(
            self._command("systemctl", "cat", unit_name),
            capture_output=True,
            text=True,
            timeout=SMB_COMMAND_TIMEOUT_SECONDS,
        )
        if cat_result.returncode != 0:
            return "unavailable"
        return status
