from typing import Optional

from simple_safer_server.adapters.command_runner import PIPE, CommandRunner


class SetupCommandAdapter:
    """Wraps setup wizard commands for disk formatting, SMB boot enable, and MEGA setup."""

    def __init__(self, command_runner: Optional[CommandRunner] = None) -> None:
        self._command_runner = command_runner or CommandRunner()

    def whole_disk_type(self, disk: str):
        return self._command_runner.run(
            ["lsblk", "-dn", "-o", "TYPE", disk],
            capture_output=True,
            text=True,
            check=True,
        )

    def create_partition(self, disk: str, fdisk_input: bytes):
        return self._command_runner.run(["fdisk", disk], input=fdisk_input, capture_output=True)

    def partprobe(self, disk: str):
        return self._command_runner.run(["partprobe", disk], capture_output=True, text=True)

    def format_ntfs(self, partition: str):
        return self._command_runner.run(
            ["mkfs.ntfs", "-f", partition], capture_output=True, text=True
        )

    def enable_smb_unit(self, unit_name: str) -> None:
        self._command_runner.run(["systemctl", "enable", unit_name], check=True)

    def obscure_rclone_password(self, password: str) -> str:
        result = self._command_runner.run(
            ["rclone", "obscure", "-"],
            input=f"{password}\n",
            stdout=PIPE,
            check=True,
            text=True,
        )
        return result.stdout.strip()

    def rclone_lsjson(self, remote_path: str, config_path: str):
        return self._command_runner.run(
            ["rclone", "lsjson", remote_path, "--config", config_path],
            capture_output=True,
            text=True,
        )

    def rclone_mkdir(self, remote_path: str, config_path: str):
        return self._command_runner.run(
            ["rclone", "mkdir", remote_path, "--config", config_path],
            capture_output=True,
            text=True,
        )
