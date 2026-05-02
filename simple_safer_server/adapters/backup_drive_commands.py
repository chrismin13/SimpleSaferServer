import os
from typing import Optional

from simple_safer_server.adapters.command_runner import CommandRunner


class BackupDriveCommandAdapter:
    """Wraps commands used while detaching the managed backup drive."""

    def __init__(self, command_runner: Optional[CommandRunner] = None) -> None:
        self._command_runner = command_runner or CommandRunner()

    # These service-control calls are intentionally best-effort: the caller
    # must not fail backup-drive rollback because a service is already stopped,
    # permissions changed mid-flow, or a remote mount disappeared. Failures are
    # surfaced by the surrounding backup/restore checks instead of raising here.
    def close_smb_share(self, mount_point: str) -> None:
        self._command_runner.run(["smbcontrol", "all", "close-share", mount_point], check=False)

    def stop_unit(self, unit_name: str) -> None:
        self._command_runner.run(["systemctl", "stop", unit_name], check=False)

    def start_unit(self, unit_name: str) -> None:
        self._command_runner.run(["systemctl", "start", unit_name], check=False)

    def unmount(self, mount_point: str):
        return self._command_runner.run(
            ["umount", mount_point],
            capture_output=True,
            text=True,
            check=False,
        )

    def unmount_partition(self, device: str):
        return self._command_runner.run(
            ["umount", device],
            capture_output=True,
            text=True,
            check=False,
        )

    def mount_ntfs(self, partition: str, mount_point: str):
        uid = os.getuid()
        gid = os.getgid()
        return self._command_runner.run(
            ["ntfs-3g", partition, mount_point, "-o", f"rw,uid={uid},gid={gid}"],
            capture_output=True,
            text=True,
        )

    def cleanup_unmount(self, device: str) -> None:
        self._command_runner.run(["umount", device], check=False)

    def find_device_by_uuid(self, uuid: str) -> str:
        # result.stdout.strip() is the contract here: blkid returns an empty
        # string when the UUID is not present, and callers must handle that.
        result = self._command_runner.run(
            ["blkid", "-t", f"UUID={uuid}", "-o", "device"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def power_down_device(self, device: str) -> None:
        self._command_runner.run(["hdparm", "-y", device], check=False)

    def blkid_filesystem_type(self, device: str):
        return self._command_runner.run(
            ["blkid", "-o", "value", "-s", "TYPE", device],
            capture_output=True,
            text=True,
        )

    def current_mounts(self):
        return self._command_runner.run(["mount"], capture_output=True, text=True)

    def lsblk_devices_json(self):
        return self._command_runner.run(
            [
                "lsblk",
                "-J",
                "-o",
                "NAME,PATH,FSTYPE,LABEL,SIZE,MODEL,MOUNTPOINT,TYPE,TRAN,RM,HOTPLUG",
            ],
            capture_output=True,
            text=True,
        )

    def system_drive(self):
        return self._command_runner.run(
            ["findmnt", "-n", "-o", "SOURCE", "/"], capture_output=True, text=True
        )

    def partition_filesystem_type(self, drive: str):
        return self._command_runner.run(
            ["lsblk", "-no", "FSTYPE", drive],
            capture_output=True,
            text=True,
        )

    def reload_systemd_mount_units(self):
        return self._command_runner.run(
            ["systemctl", "daemon-reload"],
            capture_output=True,
            text=True,
        )

    def drive_uuid(self, drive: str):
        return self._command_runner.run(
            ["blkid", "-s", "UUID", "-o", "value", drive],
            capture_output=True,
            text=True,
        )
