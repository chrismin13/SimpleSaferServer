import subprocess
from typing import Optional

from simple_safer_server.adapters.command_runner import DEVNULL, CommandRunner


class SystemdAdapter:
    """Wraps systemd and journalctl commands used by scheduled task views."""

    def __init__(self, command_runner: Optional[CommandRunner] = None) -> None:
        self._command_runner = command_runner or CommandRunner()

    def journal(self, unit_name: str, lines: int) -> str:
        result = self._command_runner.run(
            ["journalctl", "-u", unit_name, "-n", str(lines), "--no-pager"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def start_unit(self, unit_name: str) -> None:
        self._command_runner.run(
            ["systemctl", "start", unit_name, "--no-block"],
            stdout=DEVNULL,
            stderr=DEVNULL,
            check=True,
        )

    def stop_unit(self, unit_name: str) -> None:
        self._command_runner.run(
            ["systemctl", "stop", unit_name, "--no-block"],
            stdout=DEVNULL,
            stderr=DEVNULL,
            check=True,
        )

    def show_property(self, unit_name: str, property_name: str) -> str:
        result = self._command_runner.run(
            ["systemctl", "show", unit_name, f"--property={property_name}"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def show_properties(self, unit_name: str, *property_names: str) -> str:
        command = ["systemctl", "show", unit_name]
        command.extend(f"--property={property_name}" for property_name in property_names)
        result = self._command_runner.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def is_active(self, unit_name: str) -> str:
        result = self._command_runner.run(
            ["systemctl", "is-active", unit_name],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip()


CalledProcessError = subprocess.CalledProcessError
