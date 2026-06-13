from simple_safer_server.adapters.command_runner import CommandRunner

SERVER_IDENTITY_TIMEOUT_SECONDS = 30


class ServerIdentityCommandAdapter:
    """Wrap host identity commands behind one injectable boundary."""

    def __init__(self, command_runner: CommandRunner | None = None) -> None:
        self._command_runner = command_runner or CommandRunner()

    def current_hostname(self) -> str:
        result = self._command_runner.run(
            ["hostname"],
            capture_output=True,
            text=True,
            check=True,
            timeout=SERVER_IDENTITY_TIMEOUT_SECONDS,
        )
        return result.stdout.strip()

    def set_hostname(self, hostname: str) -> None:
        self._command_runner.run(
            ["hostnamectl", "set-hostname", hostname],
            check=True,
            timeout=SERVER_IDENTITY_TIMEOUT_SECONDS,
        )

    def restart_unit(self, unit_name: str) -> None:
        self._command_runner.run(
            ["systemctl", "restart", unit_name],
            check=True,
            timeout=SERVER_IDENTITY_TIMEOUT_SECONDS,
        )
