from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

from simple_safer_server.adapters.command_runner import CommandRunner

SMB_COMMAND_TIMEOUT_SECONDS = 30


class SmbCommandAdapter:
    """Wraps Samba validation, backup, service, and status commands."""

    def __init__(self, command_runner: CommandRunner | None = None) -> None:
        self._command_runner = command_runner or CommandRunner()

    def _command(self, *parts: str):
        return list(parts)

    def validate_config(self, validator: str, candidate_path: Path, cwd: Path | None = None):
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


class FakeSmbCommandAdapter:
    """Simulates Samba command behavior for fake mode without host Samba tools."""

    def __init__(self, fake_state: Any | None = None) -> None:
        self._fake_state = fake_state

    def validate_config(self, validator: str, candidate_path: Path, cwd: Path | None = None):
        # Fake mode runs on macOS and Railway where testparm/smbd are usually
        # absent. Return the candidate text so callers that parse testparm's
        # effective-config stdout still exercise the same parsing path.
        candidate_text = Path(candidate_path).read_text(encoding="utf-8")
        return CompletedProcess(
            args=[validator, str(candidate_path)],
            returncode=0,
            stdout=candidate_text,
            stderr="",
        )

    def restart_unit(self, unit_name: str) -> None:
        self._set_service_active(unit_name)

    def reload_config(self) -> None:
        self._set_service_active("smbd")

    def unit_status(self, unit_name: str) -> str:
        if self._fake_state is None:
            return "active"
        return self._fake_state.get_smb_services().get(unit_name, "unavailable")

    def _set_service_active(self, unit_name: str) -> None:
        if self._fake_state is None:
            return
        statuses = {
            "smbd": "active",
            "nmbd": "active",
            "wsdd2": "active",
            **self._fake_state.get_smb_services(),
        }
        statuses[unit_name] = "active"
        self._fake_state.set_smb_services(
            statuses["smbd"],
            statuses["nmbd"],
            statuses["wsdd2"],
        )
