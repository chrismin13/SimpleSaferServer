import os
from typing import Optional

from simple_safer_server.adapters.command_runner import CommandRunner

STORAGE_COMMAND_TIMEOUT_SECONDS = 30
STORAGE_MOUNT_TIMEOUT_SECONDS = 120


class StorageCommandAdapter:
    """Wraps system commands used by dashboard storage controls."""

    def __init__(self, command_runner: Optional[CommandRunner] = None) -> None:
        self._command_runner = command_runner or CommandRunner()

    def reboot(self) -> None:
        self._command_runner.run(["systemctl", "reboot"], check=True)

    def poweroff(self) -> None:
        self._command_runner.run(["systemctl", "poweroff"], check=True)

    def find_device_by_uuid(self, uuid: str) -> str:
        # The blkid lookup can produce no stdout for an absent UUID; returning
        # result.stdout.strip() means callers must check for an empty device path.
        result = self._command_runner.run(
            ["blkid", "-t", f"UUID={uuid}", "-o", "device"],
            capture_output=True,
            text=True,
            timeout=STORAGE_COMMAND_TIMEOUT_SECONDS,
        )
        return result.stdout.strip()

    def mount(self, device: str, mount_point: str, ntfs_driver: str = "ntfs-3g") -> None:
        uid = os.getuid()
        gid = os.getgid()
        self._command_runner.run(
            [
                "mount",
                "-t",
                ntfs_driver,
                "-o",
                f"rw,uid={uid},gid={gid}",
                device,
                mount_point,
            ],
            check=True,
            timeout=STORAGE_MOUNT_TIMEOUT_SECONDS,
        )

    def start_unit(self, unit_name: str) -> None:
        # These service restarts are best-effort after a successful mount so
        # one unavailable helper does not hide the drive from the dashboard.
        self._command_runner.run(
            ["systemctl", "start", unit_name],
            check=False,
            timeout=STORAGE_COMMAND_TIMEOUT_SECONDS,
        )
