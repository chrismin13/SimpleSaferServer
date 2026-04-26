import contextlib
import logging
import os

from backup_drive_setup import BackupDriveSetupError, _get_mount_for_partition
from runtime import get_fake_state, get_runtime
from simple_safer_server.adapters.backup_drive_commands import BackupDriveCommandAdapter

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


def _power_down_managed_backup_drive(configured_uuid, system_utils, command_adapter):
    if not configured_uuid:
        return

    try:
        partition_device = command_adapter.find_device_by_uuid(configured_uuid)
        if not partition_device:
            return

        parent_device = system_utils.get_parent_device(partition_device)
        if parent_device:
            command_adapter.power_down_device(parent_device)
    except Exception as exc:
        LOGGER.warning('Failed to power down configured backup drive: %s', exc)


def unmount_managed_backup_drive(
    configured_mount_point,
    configured_uuid,
    system_utils,
    *,
    runtime=None,
    power_down=False,
    command_adapter=None,
):
    runtime = runtime or get_runtime()
    command_adapter = command_adapter or BackupDriveCommandAdapter()
    fake_state = get_fake_state() if runtime.is_fake else None

    if runtime.is_fake:
        if fake_state is None:
            raise RuntimeError('Fake runtime is missing fake state.')
        fake_state.set_mount(False)
        return

    configured_mount_point = (configured_mount_point or '').strip()
    if not configured_mount_point:
        raise BackupDriveSetupError('Configured backup mount point is missing.')

    # The managed backup-drive path is intentionally broader than an exact
    # partition umount because Samba and background jobs can keep busy handles
    # on the share even when the user only asked to unmount one partition.
    with contextlib.suppress(Exception):
        command_adapter.close_smb_share(configured_mount_point)

    for service in MANAGED_BACKUP_UNMOUNT_TASKS:
        command_adapter.stop_unit(service)
    command_adapter.stop_unit('smbd')
    command_adapter.stop_unit('nmbd')

    try:
        result = command_adapter.unmount(configured_mount_point)
        if result.returncode != 0:
            raise BackupDriveSetupError(
                'Failed to unmount drive: {}'.format(
                    result.stderr.strip() if result.stderr else 'unknown error'
                )
            )

        if power_down:
            _power_down_managed_backup_drive(configured_uuid, system_utils, command_adapter)
    finally:
        with contextlib.suppress(Exception):
            command_adapter.start_unit('smbd')
            command_adapter.start_unit('nmbd')
