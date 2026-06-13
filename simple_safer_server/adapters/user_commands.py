from simple_safer_server.adapters.command_runner import CalledProcessError, CommandRunner

USER_COMMAND_TIMEOUT_SECONDS = 30


class UserCommandAdapter:
    """Wraps local account and Samba account commands used by UserManager."""

    def __init__(self, command_runner: CommandRunner | None = None) -> None:
        self._command_runner = command_runner or CommandRunner()

    def system_user_exists(self, username: str) -> bool:
        try:
            self._command_runner.run(
                ["id", username],
                check=True,
                capture_output=True,
                timeout=USER_COMMAND_TIMEOUT_SECONDS,
            )
            return True
        except CalledProcessError:
            return False

    def create_system_user(self, username: str) -> None:
        self._command_runner.run(
            ["useradd", "-m", "-s", "/bin/bash", username],
            check=True,
            timeout=USER_COMMAND_TIMEOUT_SECONDS,
        )

    def samba_users(self) -> set[str]:
        result = self._command_runner.run(
            ["pdbedit", "-L"],
            capture_output=True,
            text=True,
            timeout=USER_COMMAND_TIMEOUT_SECONDS,
        )
        return {
            line.split(":", 1)[0].strip() for line in result.stdout.splitlines() if line.strip()
        }

    def set_samba_password(self, username: str, password: str) -> None:
        self._command_runner.run(
            ["smbpasswd", "-s", "-a", username],
            input=f"{password}\n{password}\n",
            text=True,
            check=True,
            timeout=USER_COMMAND_TIMEOUT_SECONDS,
        )

    def remove_samba_user(self, username: str) -> None:
        self._command_runner.run(
            ["smbpasswd", "-x", username],
            check=True,
            timeout=USER_COMMAND_TIMEOUT_SECONDS,
        )
