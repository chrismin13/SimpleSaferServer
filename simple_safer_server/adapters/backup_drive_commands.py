import os
from typing import Optional

from simple_safer_server.adapters.command_runner import CommandRunner

BACKUP_DRIVE_COMMAND_TIMEOUT_SECONDS = 30
BACKUP_DRIVE_MOUNT_TIMEOUT_SECONDS = 120


class BackupDriveCommandAdapter:
    """Wraps commands used while detaching the managed backup drive."""

    def __init__(self, command_runner: Optional[CommandRunner] = None) -> None:
        self._command_runner = command_runner or CommandRunner()

    # These service-control calls are intentionally best-effort: the caller
    # must not fail backup-drive rollback because a service is already stopped,
    # permissions changed mid-flow, or a remote mount disappeared. Failures are
    # surfaced by the surrounding backup/restore checks instead of raising here.
    def close_smb_share(self, mount_point: str) -> None:
        self._command_runner.run(
            ["smbcontrol", "all", "close-share", mount_point],
            check=False,
            timeout=BACKUP_DRIVE_COMMAND_TIMEOUT_SECONDS,
        )

    def stop_unit(self, unit_name: str) -> None:
        self._command_runner.run(
            ["systemctl", "stop", unit_name],
            check=False,
            timeout=BACKUP_DRIVE_COMMAND_TIMEOUT_SECONDS,
        )

    def start_unit(self, unit_name: str) -> None:
        self._command_runner.run(
            ["systemctl", "start", unit_name],
            check=False,
            timeout=BACKUP_DRIVE_COMMAND_TIMEOUT_SECONDS,
        )

    def unmount(self, mount_point: str):
        return self._command_runner.run(
            ["umount", mount_point],
            capture_output=True,
            text=True,
            check=False,
            timeout=BACKUP_DRIVE_MOUNT_TIMEOUT_SECONDS,
        )

    def unmount_partition(self, device: str):
        return self._command_runner.run(
            ["umount", device],
            capture_output=True,
            text=True,
            check=False,
            timeout=BACKUP_DRIVE_MOUNT_TIMEOUT_SECONDS,
        )

    def mount_ntfs(self, partition: str, mount_point: str, ntfs_driver: str = "ntfs-3g"):
        uid = os.getuid()
        gid = os.getgid()
        if ntfs_driver == "ntfs3":
            # Match the managed fstab entry so the immediate validation mount
            # has the same Samba-friendly permission view as later remounts.
            mount_options = "rw,uid=0,gid=0,dmask=000,fmask=000"
            command = ["mount", "-t", "ntfs3", partition, mount_point, "-o", mount_options]
        else:
            mount_options = f"rw,uid={uid},gid={gid}"
            # ntfs-3g stays the default because it has the longest compatibility
            # history across the Debian/Ubuntu releases SimpleSaferServer supports.
            command = ["ntfs-3g", partition, mount_point, "-o", mount_options]
        return self._command_runner.run(
            command,
            capture_output=True,
            text=True,
            timeout=BACKUP_DRIVE_MOUNT_TIMEOUT_SECONDS,
        )

    def cleanup_unmount(self, device: str) -> None:
        self._command_runner.run(
            ["umount", device],
            check=False,
            timeout=BACKUP_DRIVE_MOUNT_TIMEOUT_SECONDS,
        )

    def find_device_by_uuid(self, uuid: str) -> str:
        # result.stdout.strip() is the contract here: blkid returns an empty
        # string when the UUID is not present, and callers must handle that.
        result = self._command_runner.run(
            ["blkid", "-t", f"UUID={uuid}", "-o", "device"],
            capture_output=True,
            text=True,
            timeout=BACKUP_DRIVE_COMMAND_TIMEOUT_SECONDS,
        )
        return result.stdout.strip()

    def power_down_device(self, device: str) -> None:
        self._command_runner.run(
            ["hdparm", "-y", device],
            check=False,
            timeout=BACKUP_DRIVE_COMMAND_TIMEOUT_SECONDS,
        )

    def blkid_filesystem_type(self, device: str):
        return self._command_runner.run(
            ["blkid", "-o", "value", "-s", "TYPE", device],
            capture_output=True,
            text=True,
            timeout=BACKUP_DRIVE_COMMAND_TIMEOUT_SECONDS,
        )

    def current_mounts(self):
        return self._command_runner.run(
            ["mount"],
            capture_output=True,
            text=True,
            timeout=BACKUP_DRIVE_COMMAND_TIMEOUT_SECONDS,
        )

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
            timeout=BACKUP_DRIVE_COMMAND_TIMEOUT_SECONDS,
        )

    def system_drive(self):
        return self._command_runner.run(
            ["findmnt", "-n", "-o", "SOURCE", "/"],
            capture_output=True,
            text=True,
            timeout=BACKUP_DRIVE_COMMAND_TIMEOUT_SECONDS,
        )

    def partition_filesystem_type(self, drive: str):
        return self._command_runner.run(
            ["lsblk", "-no", "FSTYPE", drive],
            capture_output=True,
            text=True,
            timeout=BACKUP_DRIVE_COMMAND_TIMEOUT_SECONDS,
        )

    def reload_systemd_mount_units(self):
        return self._command_runner.run(
            ["systemctl", "daemon-reload"],
            capture_output=True,
            text=True,
            timeout=BACKUP_DRIVE_COMMAND_TIMEOUT_SECONDS,
        )

    def drive_uuid(self, drive: str):
        return self._command_runner.run(
            ["blkid", "-s", "UUID", "-o", "value", drive],
            capture_output=True,
            text=True,
            timeout=BACKUP_DRIVE_COMMAND_TIMEOUT_SECONDS,
        )
