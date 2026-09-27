import os

from simple_safer_server.adapters.command_runner import PIPE, CommandRunner

# Relative local paths can also be hidden behind alias/crypt remotes. Match the
# production backup script's working directory for every rclone process, including RC.
RCLONE_WORKING_DIRECTORY = "/"


def managed_rclone_environment() -> dict[str, str]:
    """Keep managed config authoritative while retaining unrelated process settings."""
    # The editor and sync must resolve the same credentials and destination.
    # Ambient remote/backend overrides can otherwise redirect a destructive sync.
    # Callers may add their own private RC authentication after this filtering.
    return {key: value for key, value in os.environ.items() if not key.startswith('RCLONE_')}


class RcloneAdapter:
    """Wraps rclone process creation so backup services do not own subprocess details."""

    def __init__(self, command_runner: CommandRunner | None = None) -> None:
        self._command_runner = command_runner or CommandRunner()

    def sync(
        self,
        source: str,
        destination: str,
        *,
        config_path: str | None = None,
        bandwidth_limit: str = "",
    ):
        command = self.build_sync_command(
            source,
            destination,
            config_path=config_path,
            bandwidth_limit=bandwidth_limit,
        )
        return self._command_runner.popen(
            command,
            stdout=PIPE,
            stderr=PIPE,
            text=True,
            bufsize=1,
            env=managed_rclone_environment(),
            cwd=RCLONE_WORKING_DIRECTORY,
        )

    @staticmethod
    def build_sync_command(
        source: str,
        destination: str,
        *,
        config_path: str | None = None,
        bandwidth_limit: str = "",
    ) -> list[str]:
        command = ["rclone", "sync", source, destination, "--create-empty-src-dirs", "-v"]
        if config_path:
            command.extend(["--config", config_path])
        if bandwidth_limit:
            command.extend(["--bwlimit", bandwidth_limit])
        return command
