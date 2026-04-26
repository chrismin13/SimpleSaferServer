from typing import List, Optional

from simple_safer_server.adapters.command_runner import PIPE, CommandRunner


class RcloneAdapter:
    """Wraps rclone process creation so backup services do not own subprocess details."""

    def __init__(self, command_runner: Optional[CommandRunner] = None) -> None:
        self._command_runner = command_runner or CommandRunner()

    def sync(
        self,
        source: str,
        destination: str,
        *,
        config_path: Optional[str] = None,
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
        )

    @staticmethod
    def build_sync_command(
        source: str,
        destination: str,
        *,
        config_path: Optional[str] = None,
        bandwidth_limit: str = "",
    ) -> List[str]:
        command = ["rclone", "sync", source, destination, "--create-empty-src-dirs", "-v"]
        if config_path:
            command.extend(["--config", config_path])
        if bandwidth_limit:
            command.extend(["--bwlimit", bandwidth_limit])
        return command
