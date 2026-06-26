from pathlib import Path

from simple_safer_server.adapters.command_runner import (
    DEVNULL,
    CommandRunner,
)

SYSTEM_UPDATES_SUPPORT_TIMEOUT_SECONDS = 60


class SystemUpdatesCommandAdapter:
    """Wraps read-only package-manager and Livepatch status commands."""

    def __init__(
        self,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self._command_runner = command_runner or CommandRunner()

    def is_lock_held(self, fuser_binary: str, path: Path) -> bool:
        result = self._command_runner.run(
            [fuser_binary, str(path)],
            stdout=DEVNULL,
            stderr=DEVNULL,
            timeout=SYSTEM_UPDATES_SUPPORT_TIMEOUT_SECONDS,
        )
        return result.returncode == 0

    def livepatch_status_json(self, binary: str):
        return self._command_runner.run(
            [binary, "status", "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=SYSTEM_UPDATES_SUPPORT_TIMEOUT_SECONDS,
        )

    def livepatch_status_text(self, binary: str):
        return self._command_runner.run(
            [binary, "status"],
            capture_output=True,
            text=True,
            check=False,
            timeout=SYSTEM_UPDATES_SUPPORT_TIMEOUT_SECONDS,
        )
