from typing import Optional, Set

from simple_safer_server.adapters.command_runner import CalledProcessError, CommandRunner


class UserCommandAdapter:
    """Wraps local account and Samba account commands used by UserManager."""

    def __init__(self, command_runner: Optional[CommandRunner] = None) -> None:
        self._command_runner = command_runner or CommandRunner()

    def system_user_exists(self, username: str) -> bool:
        try:
            self._command_runner.run(["id", username], check=True, capture_output=True)
            return True
        except CalledProcessError:
            return False

    def create_system_user(self, username: str) -> None:
        self._command_runner.run(["sudo", "useradd", "-m", "-s", "/bin/bash", username], check=True)

    def samba_users(self) -> Set[str]:
        result = self._command_runner.run(["sudo", "pdbedit", "-L"], capture_output=True, text=True)
        return {
            line.split(":", 1)[0].strip() for line in result.stdout.splitlines() if line.strip()
        }

    def set_samba_password(self, username: str, password: str) -> None:
        self._command_runner.run(
            ["sudo", "smbpasswd", "-s", "-a", username],
            input=f"{password}\n{password}\n",
            text=True,
            check=True,
        )

    def remove_samba_user(self, username: str) -> None:
        self._command_runner.run(["sudo", "smbpasswd", "-x", username], check=True)
