import subprocess

from simple_safer_server.adapters.command_runner import DEVNULL, CommandRunner

SYSTEMD_COMMAND_TIMEOUT_SECONDS = 30


class SystemdAdapter:
    """Wraps systemd and journalctl commands used by scheduled task views."""

    def __init__(self, command_runner: CommandRunner | None = None) -> None:
        self._command_runner = command_runner or CommandRunner()

    def journal(self, unit_name: str, lines: int) -> str:
        result = self._command_runner.run(
            ["journalctl", "-a", "-u", unit_name, "-n", str(lines), "--no-pager"],
            capture_output=True,
            text=True,
            check=True,
            timeout=SYSTEMD_COMMAND_TIMEOUT_SECONDS,
        )
        return result.stdout

    def start_unit(self, unit_name: str) -> None:
        self._command_runner.run(
            ["systemctl", "start", unit_name, "--no-block"],
            stdout=DEVNULL,
            stderr=DEVNULL,
            check=True,
            timeout=SYSTEMD_COMMAND_TIMEOUT_SECONDS,
        )

    def stop_unit(self, unit_name: str) -> None:
        self._command_runner.run(
            ["systemctl", "stop", unit_name, "--no-block"],
            stdout=DEVNULL,
            stderr=DEVNULL,
            check=True,
            timeout=SYSTEMD_COMMAND_TIMEOUT_SECONDS,
        )

    def disable_timer_now(self, unit_name: str) -> None:
        self._command_runner.run(
            ["systemctl", "disable", "--now", unit_name],
            stdout=DEVNULL,
            stderr=DEVNULL,
            check=True,
            timeout=SYSTEMD_COMMAND_TIMEOUT_SECONDS,
        )

    def enable_timer_now(self, unit_name: str) -> None:
        self._command_runner.run(
            ["systemctl", "enable", "--now", unit_name],
            stdout=DEVNULL,
            stderr=DEVNULL,
            check=True,
            timeout=SYSTEMD_COMMAND_TIMEOUT_SECONDS,
        )

    def show_property(self, unit_name: str, property_name: str) -> str:
        result = self._command_runner.run(
            ["systemctl", "show", unit_name, f"--property={property_name}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=SYSTEMD_COMMAND_TIMEOUT_SECONDS,
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
            timeout=SYSTEMD_COMMAND_TIMEOUT_SECONDS,
        )
        return result.stdout

    def is_active(self, unit_name: str) -> str:
        result = self._command_runner.run(
            ["systemctl", "is-active", unit_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=SYSTEMD_COMMAND_TIMEOUT_SECONDS,
        )
        return result.stdout.strip()


CalledProcessError = subprocess.CalledProcessError
