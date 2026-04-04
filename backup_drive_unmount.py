import logging
import os
import subprocess

from backup_drive_setup import BackupDriveSetupError, _get_mount_for_partition
from runtime import get_fake_state, get_runtime


LOGGER = logging.getLogger(__name__)
MANAGED_BACKUP_UNMOUNT_TASKS = (
    'check_mount.service',
    'check_health.service',
    'backup_cloud.service',
)


def is_selected_partition_managed_backup_drive(
    partition_path,
    configured_mount_point,
    configured_uuid,
    system_utils,
    runtime=None,
):
    runtime = runtime or get_runtime()
    configured_mount_point = (configured_mount_point or '').strip()
    if not partition_path or not configured_mount_point:
        return False

    if runtime.is_fake:
        return system_utils.is_mounted(configured_mount_point)

    mount = _get_mount_for_partition(partition_path)
    if not mount:
        return False

    # Keep the SMB-safe path tied to the partition that is actually mounted at
    # the managed backup mount point. UUID-only matching sounds convenient, but
    # cloned replacement disks can legitimately share a filesystem UUID and
    # would make us stop SMB for the wrong physical device.
    return os.path.realpath(mount['mount_point']) == os.path.realpath(configured_mount_point)


def _power_down_managed_backup_drive(configured_uuid, system_utils):
    if not configured_uuid:
        return

    try:
        blkid_out = subprocess.run(
            ['blkid', '-t', f'UUID={configured_uuid}', '-o', 'device'],
            capture_output=True,
            text=True,
        )
        partition_device = blkid_out.stdout.strip()
        if not partition_device:
            return

        parent_device = system_utils.get_parent_device(partition_device)
        if parent_device:
            subprocess.run(['sudo', 'hdparm', '-y', parent_device], check=False)
    except Exception as exc:
        LOGGER.warning('Failed to power down configured backup drive: %s', exc)


def unmount_managed_backup_drive(
    configured_mount_point,
    configured_uuid,
    system_utils,
    *,
    runtime=None,
    power_down=False,
):
    runtime = runtime or get_runtime()
    fake_state = get_fake_state() if runtime.is_fake else None

    if runtime.is_fake:
        fake_state.set_mount(False)
        return

    configured_mount_point = (configured_mount_point or '').strip()
    if not configured_mount_point:
        raise BackupDriveSetupError('Configured backup mount point is missing.')

    # The managed backup-drive path is intentionally broader than an exact
    # partition umount because Samba and background jobs can keep busy handles
    # on the share even when the user only asked to unmount one partition.
    try:
        subprocess.run(['sudo', 'smbcontrol', 'all', 'close-share', configured_mount_point], check=False)
    except Exception:
        pass

    for service in MANAGED_BACKUP_UNMOUNT_TASKS:
        subprocess.run(['sudo', 'systemctl', 'stop', service], check=False)
    subprocess.run(['sudo', 'systemctl', 'stop', 'smbd'], check=False)
    subprocess.run(['sudo', 'systemctl', 'stop', 'nmbd'], check=False)

    try:
        result = subprocess.run(
            ['sudo', 'umount', configured_mount_point],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise BackupDriveSetupError(
                'Failed to unmount drive: {}'.format(
                    result.stderr.strip() if result.stderr else 'unknown error'
                )
            )

        if power_down:
            _power_down_managed_backup_drive(configured_uuid, system_utils)
    finally:
        try:
            subprocess.run(['sudo', 'systemctl', 'start', 'smbd'], check=False)
            subprocess.run(['sudo', 'systemctl', 'start', 'nmbd'], check=False)
        except Exception:
            pass
