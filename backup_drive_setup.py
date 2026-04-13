import logging
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from runtime import get_fake_state, get_runtime


LOGGER = logging.getLogger(__name__)
FSTAB_MARKER = "# SimpleSaferServer managed backup drive"
LEGACY_FSTAB_MARKER = "SimpleSaferServer"
NTFS_FILESYSTEM_TYPES = {'ntfs', 'ntfs3', 'ntfs-3g'}


class BackupDriveSetupError(Exception):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details


def _get_fstab_path(runtime=None, fstab_path=None):
    runtime = runtime or get_runtime()
    if fstab_path is not None:
        return Path(fstab_path)
    if runtime.is_fake:
        return runtime.data_dir / 'fstab'
    return Path('/etc/fstab')


def _is_managed_fstab_line(line):
    stripped = line.strip()
    if not stripped or stripped.startswith('#'):
        return False
    if '#' not in line:
        return False
    marker = line.split('#', 1)[1].strip()
    return marker in {
        FSTAB_MARKER.lstrip('# ').strip(),
        LEGACY_FSTAB_MARKER,
    }


def _parse_fstab_entry(line):
    stripped = line.strip()
    if not stripped or stripped.startswith('#'):
        return None

    content = stripped.split('#', 1)[0].strip()
    if not content:
        return None

    parts = re.split(r'\s+', content)
    if len(parts) < 2:
        return None

    return {
        'spec': parts[0],
        'mount_point': parts[1],
    }


def _backup_file(path, runtime, prefix):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = runtime.config_dir / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / '{}.{}'.format(prefix, timestamp)
    shutil.copy2(path, backup_path)
    return backup_path


def _is_ntfs_filesystem(filesystem_type):
    return (filesystem_type or '').strip().lower() in NTFS_FILESYSTEM_TYPES


def _get_blkid_filesystem_type(device_path):
    # lsblk can report a mounted ntfs-3g partition as "fuseblk", which tells
    # us how it is mounted right now rather than what is on disk. For the
    # NTFS-only picker we verify that narrower case with blkid so we do not
    # accidentally treat every FUSE-backed block device as NTFS months later.
    result = subprocess.run(
        ['blkid', '-o', 'value', '-s', 'TYPE', device_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ''
    return result.stdout.strip().lower()


def _get_partition_type_for_scan(device_path, filesystem_type, fallback_type='', ntfs_only=False):
    normalized_type = (filesystem_type or '').strip().lower()
    if not ntfs_only:
        return filesystem_type or fallback_type or 'unknown'

    if _is_ntfs_filesystem(normalized_type):
        # The NTFS-only pickers care about "mountable backup target" rather
        # than which exact driver spelling lsblk reported today.
        return 'ntfs'

    if normalized_type == 'fuseblk' and _get_blkid_filesystem_type(device_path) == 'ntfs':
        # This is an API contract for UI consumers, not a claim that the volume
        # is mounted with the in-kernel NTFS driver.
        return 'ntfs'

    return None


def _normalize_device_path(device_path):
    device_path = (device_path or '').strip()
    if not device_path:
        return ''
    return os.path.realpath(device_path)


def _lsblk_flag_is_true(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def _get_drive_connection_type(block):
    transport = (block.get('tran') or '').strip().lower()
    if transport == 'usb':
        return 'usb'

    # External-drive enclosures are not perfectly consistent across kernels
    # and bridge chipsets, so keep a fallback for hotplug/removable signals
    # rather than assuming every non-USB transport is an internal disk.
    if _lsblk_flag_is_true(block.get('hotplug')) or _lsblk_flag_is_true(block.get('rm')):
        return 'removable'

    return 'internal'


def _get_current_mounts():
    # Use the live mount table for operation safety checks instead of lsblk's
    # mountpoint field so we always act on what the kernel currently reports.
    mount_check = subprocess.run(['mount'], capture_output=True, text=True)
    mounts = []
    for line in mount_check.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            mounts.append({'device': parts[0], 'mount_point': parts[2]})
    return mounts


def _load_lsblk_devices():
    # Keep one shared inventory source for both setup and rerun flows. The
    # flows differ in target semantics, not in how we discover block devices.
    lsblk_result = subprocess.run(
        ['lsblk', '-J', '-o', 'NAME,PATH,FSTYPE,LABEL,SIZE,MODEL,MOUNTPOINT,TYPE,TRAN,RM,HOTPLUG'],
        capture_output=True,
        text=True,
    )
    if lsblk_result.returncode != 0:
        raise BackupDriveSetupError('Failed to list drives.')

    try:
        lsblk_data = json.loads(lsblk_result.stdout)
    except Exception as exc:
        raise BackupDriveSetupError('Failed to parse drive list.') from exc

    return lsblk_data.get('blockdevices', [])


def _get_system_drive_path():
    root_mount = subprocess.run(['findmnt', '-n', '-o', 'SOURCE', '/'], capture_output=True, text=True)
    return root_mount.stdout.strip() if root_mount.returncode == 0 else None


def _iter_non_system_disks(blockdevices, system_drive=None):
    for block in blockdevices:
        if block.get('type') != 'disk':
            continue
        disk_path = block.get('path')
        if not disk_path:
            continue
        if system_drive and system_drive.startswith(disk_path):
            continue
        yield block


def _find_disk_device(disk_path, blockdevices):
    normalized_disk = _normalize_device_path(disk_path)
    for block in blockdevices:
        if block.get('type') != 'disk':
            continue
        if _normalize_device_path(block.get('path')) == normalized_disk:
            return block
    return None


def _get_disk_member_devices(disk_path, blockdevices):
    # Setup step 2 operates on a whole disk, so it must consider every child
    # partition that belongs to that disk before unmounting or formatting.
    disk = _find_disk_device(disk_path, blockdevices)
    if not disk:
        return set()

    device_paths = set()
    for child in disk.get('children', []) or []:
        child_path = child.get('path')
        if child_path:
            device_paths.add(_normalize_device_path(child_path))

    # Some removable media expose a filesystem directly on the disk path.
    if not device_paths and disk.get('fstype'):
        device_paths.add(_normalize_device_path(disk.get('path')))

    return device_paths


def _get_mounted_partitions_for_disk(disk_path, blockdevices=None, mounts=None):
    # Disk operations intentionally match child partitions; partition-oriented
    # flows use _get_mount_for_partition() instead.
    blockdevices = blockdevices if blockdevices is not None else _load_lsblk_devices()
    mounts = mounts if mounts is not None else _get_current_mounts()
    member_devices = _get_disk_member_devices(disk_path, blockdevices)
    if not member_devices:
        return []

    mounted_partitions = []
    for mount in mounts:
        if _normalize_device_path(mount['device']) in member_devices:
            mounted_partitions.append(mount)
    return mounted_partitions


def _get_mount_for_partition(partition_path, mounts=None):
    # Rerun/setup-mount flows select an exact partition path, so this lookup
    # must never treat /dev/sdb1 and /dev/sdb11 as interchangeable.
    mounts = mounts if mounts is not None else _get_current_mounts()
    normalized_partition = _normalize_device_path(partition_path)
    for mount in mounts:
        if _normalize_device_path(mount['device']) == normalized_partition:
            return mount
    return None


def _get_partition_filesystem_type(drive):
    lsblk_result = subprocess.run(
        ['lsblk', '-no', 'FSTYPE', drive],
        capture_output=True,
        text=True,
    )
    if lsblk_result.returncode != 0:
        error_msg = lsblk_result.stderr.strip() if lsblk_result.stderr else 'Unknown error occurred'
        raise BackupDriveSetupError('Failed to determine the selected partition filesystem: {}'.format(error_msg))
    return lsblk_result.stdout.strip()


def _validate_fstab_file(path):
    issues = []
    for line_number, raw_line in enumerate(path.read_text().splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        content = stripped.split('#', 1)[0].strip()
        if not content:
            continue

        parts = re.split(r'\s+', content)
        if len(parts) < 6:
            issues.append('line {} does not have 6 fstab fields: {}'.format(line_number, raw_line.strip()))
            continue

        spec, mount_point, fstype = parts[0], parts[1], parts[2]
        if _is_managed_fstab_line(raw_line):
            if not mount_point.startswith('/'):
                issues.append('line {} has a non-absolute managed mount point: {}'.format(line_number, mount_point))
            if not spec.startswith('UUID='):
                issues.append('line {} has an invalid managed UUID spec: {}'.format(line_number, spec))
            if fstype != 'ntfs-3g':
                issues.append('line {} has unexpected managed filesystem type: {}'.format(line_number, fstype))

    if issues:
        details = '\n'.join(issues)
        return False, issues[0], details

    return True, None, None


def _render_managed_fstab_entry(uuid, mount_point):
    return 'UUID={}\t\t{}\tntfs-3g\tdefaults,nofail\t0\t0 {}\n'.format(uuid, mount_point, FSTAB_MARKER)


def update_managed_fstab(uuid, mount_point, auto_mount, runtime=None, fstab_path=None):
    runtime = runtime or get_runtime()
    path = _get_fstab_path(runtime, fstab_path=fstab_path)

    if runtime.is_fake:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text().splitlines(True) if path.exists() else []
    else:
        existing = path.read_text().splitlines(True)

    managed_lines = [line for line in existing if _is_managed_fstab_line(line)]
    if len(managed_lines) > 1:
        raise BackupDriveSetupError(
            'Multiple SimpleSaferServer-managed /etc/fstab entries were found. Clean them up manually before rerunning drive setup.'
        )

    desired_spec = 'UUID={}'.format(uuid)
    if auto_mount:
        conflicts = []
        for line in existing:
            if _is_managed_fstab_line(line):
                continue
            entry = _parse_fstab_entry(line)
            if not entry:
                continue
            if entry['mount_point'] == mount_point:
                conflicts.append('mount point {}'.format(mount_point))
            if entry['spec'] == desired_spec:
                conflicts.append('UUID {}'.format(uuid))

        if conflicts:
            raise BackupDriveSetupError(
                'An existing non-SimpleSaferServer /etc/fstab entry already uses {}. Resolve it manually before rerunning drive setup.'.format(
                    ', '.join(sorted(set(conflicts)))
                )
            )

    new_lines = []
    managed_written = False
    for line in existing:
        if _is_managed_fstab_line(line):
            if auto_mount:
                new_lines.append(_render_managed_fstab_entry(uuid, mount_point))
                managed_written = True
            continue
        new_lines.append(line)

    if auto_mount and not managed_written:
        if new_lines and not new_lines[-1].endswith('\n'):
            new_lines[-1] = new_lines[-1] + '\n'
        new_lines.append(_render_managed_fstab_entry(uuid, mount_point))

    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile('w', delete=False, dir=str(path.parent), prefix='fstab-', suffix='.tmp') as handle:
        handle.writelines(new_lines)
        temp_path = Path(handle.name)

    valid, validation_error, validation_details = _validate_fstab_file(temp_path)
    if not valid:
        if temp_path.exists():
            temp_path.unlink()
        if validation_details:
            LOGGER.error('Backup drive fstab validation failed for %s:\n%s', temp_path, validation_details)
        raise BackupDriveSetupError(
            '/etc/fstab validation failed: {}'.format(validation_error),
            details=validation_details,
        )

    backup_path = None
    if path.exists():
        backup_path = _backup_file(path, runtime, 'fstab')
    shutil.move(str(temp_path), str(path))
    if not runtime.is_fake:
        path.chmod(0o644)
    return backup_path


def restore_fstab_backup(backup_path, runtime=None, fstab_path=None):
    runtime = runtime or get_runtime()
    if not backup_path:
        return
    path = _get_fstab_path(runtime, fstab_path=fstab_path)
    shutil.copy2(backup_path, path)


def _reload_systemd_mount_units(runtime=None):
    runtime = runtime or get_runtime()
    if runtime.is_fake:
        return

    # Keep daemon-reload outside update_managed_fstab() so callers can treat
    # "rewrite /etc/fstab" and "refresh systemd's generated mount units" as
    # one rollback-aware transaction.
    result = subprocess.run(
        ['systemctl', 'daemon-reload'],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise BackupDriveSetupError(
            'Failed to reload systemd after updating /etc/fstab: {}'.format(
                result.stderr.strip() if result.stderr else 'unknown error'
            )
        )


def get_drive_uuid(drive):
    result = subprocess.run(['blkid', '-s', 'UUID', '-o', 'value', drive], capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        raise BackupDriveSetupError('Could not determine the UUID for {}.'.format(drive))
    return result.stdout.strip()


def get_drive_usb_id(drive):
    try:
        sys_block_path = '/sys/class/block/{}/device'.format(os.path.basename(drive))
        parent = os.path.realpath(sys_block_path)
        while parent != '/':
            id_vendor_path = os.path.join(parent, 'idVendor')
            id_product_path = os.path.join(parent, 'idProduct')
            if os.path.isfile(id_vendor_path) and os.path.isfile(id_product_path):
                with open(id_vendor_path) as vendor_file:
                    vendor = vendor_file.read().strip()
                with open(id_product_path) as product_file:
                    product = product_file.read().strip()
                return '{}:{}'.format(vendor, product)
            parent = os.path.dirname(parent)
    except Exception as exc:
        LOGGER.warning('Failed to determine USB ID for %s: %s', drive, exc)
    return ''


def list_available_drives(runtime=None, ntfs_only=False):
    runtime = runtime or get_runtime()
    fake_state = get_fake_state() if runtime.is_fake else None

    if runtime.is_fake:
        return fake_state.get_virtual_drives()

    blockdevices = _load_lsblk_devices()
    system_drive = _get_system_drive_path()

    drives = []
    for block in _iter_non_system_disks(blockdevices, system_drive=system_drive):
        disk_path = block.get('path')
        partitions = []
        for child in block.get('children', []) or []:
            child_path = child.get('path')
            if not child_path:
                continue
            filesystem_type = child.get('fstype') or ''
            partition_type = _get_partition_type_for_scan(
                child_path,
                filesystem_type,
                fallback_type=child.get('type') or 'unknown',
                ntfs_only=ntfs_only,
            )
            if partition_type is None:
                continue
            partitions.append({
                'path': child_path,
                'type': partition_type,
                'label': child.get('label') or '',
                'size': child.get('size') or '',
                'mountpoint': child.get('mountpoint') or '',
            })

        block_filesystem_type = block.get('fstype') or ''
        should_include_whole_disk_target = ntfs_only or bool(
            block_filesystem_type or block.get('mountpoint')
        )
        block_partition_type = None
        if should_include_whole_disk_target:
            block_partition_type = _get_partition_type_for_scan(
                disk_path,
                block_filesystem_type,
                fallback_type=block.get('type') or 'unknown',
                ntfs_only=ntfs_only,
            )
        if not partitions and block_partition_type is not None:
            partitions.append({
                'path': disk_path,
                'type': block_partition_type,
                'label': block.get('label') or '',
                'size': block.get('size') or '',
                'mountpoint': block.get('mountpoint') or '',
            })

        if ntfs_only and not partitions:
            continue

        drives.append({
            'path': disk_path,
            'model': (block.get('model') or 'Unknown Drive').strip() or 'Unknown Drive',
            'size': block.get('size') or '',
            # The setup UI expects a connection hint here so operators can
            # distinguish likely external backup targets from internal disks.
            'type': _get_drive_connection_type(block),
            'device_type': block.get('type') or 'unknown',
            'partitions': partitions,
        })

    return drives


def unmount_disk_partitions(disk_path, runtime=None):
    runtime = runtime or get_runtime()
    fake_state = get_fake_state() if runtime.is_fake else None

    if runtime.is_fake:
        fake_state.set_mount(False)
        return 'Fake backup source disconnected.'

    if not disk_path:
        raise BackupDriveSetupError('No disk selected.')

    # The format flow needs to clear every mounted child partition on the
    # selected disk, not just one exact device path.
    mounted_partitions = _get_mounted_partitions_for_disk(disk_path)

    if not mounted_partitions:
        raise BackupDriveSetupError('The selected disk has no mounted partitions.')

    failures = []
    for partition in mounted_partitions:
        result = subprocess.run(['umount', partition['device']], capture_output=True, text=True)
        if result.returncode != 0:
            failures.append('{}: {}'.format(
                partition['device'],
                result.stderr.strip() if result.stderr else 'unknown error',
            ))

    if failures:
        raise BackupDriveSetupError('Failed to unmount partitions: {}'.format('; '.join(failures)))

    return 'Successfully unmounted {} partition(s).'.format(len(mounted_partitions))


def unmount_selected_partition(partition_path, runtime=None):
    runtime = runtime or get_runtime()
    fake_state = get_fake_state() if runtime.is_fake else None

    if runtime.is_fake:
        fake_state.set_mount(False)
        return 'Fake backup source disconnected.'

    if not partition_path:
        raise BackupDriveSetupError('No partition selected.')

    # The rerun flow should only unmount the exact partition the user chose.
    mount = _get_mount_for_partition(partition_path)
    if not mount:
        raise BackupDriveSetupError('The selected partition is not currently mounted.')

    result = subprocess.run(['umount', mount['device']], capture_output=True, text=True)
    if result.returncode != 0:
        raise BackupDriveSetupError(
            'Failed to unmount partition: {}'.format(
                result.stderr.strip() if result.stderr else 'unknown error'
            )
        )

    return 'Successfully unmounted {}.'.format(mount['device'])


def _sync_backup_share_path(smb_manager, new_path):
    share = smb_manager.get_managed_share('backup')
    if share:
        # Only rewrite the owned backup share. Older untagged shares are
        # deliberately left alone until the user converts them manually.
        smb_manager.update_managed_share(
            old_name='backup',
            new_name='backup',
            path=new_path,
            writable=share.get('writable', True),
            comment=share.get('comment', ''),
            valid_users=share.get('valid_users', []),
        )
        return True
    return False


def apply_backup_drive_configuration(partition, mount_point, auto_mount, config_manager, smb_manager, runtime=None):
    runtime = runtime or get_runtime()
    fake_state = get_fake_state() if runtime.is_fake else None

    mount_point = (mount_point or '').strip()
    if not mount_point or not mount_point.startswith('/'):
        raise BackupDriveSetupError('Mount point must be an absolute path.')

    previous_mount_point = config_manager.get_value('backup', 'mount_point', runtime.default_mount_point)
    previous_uuid = config_manager.get_value('backup', 'uuid', '')
    previous_usb_id = config_manager.get_value('backup', 'usb_id', '')

    if runtime.is_fake:
        selected_path = Path(os.path.abspath(mount_point or runtime.default_mount_point))
        if not selected_path.exists():
            try:
                selected_path.relative_to(runtime.data_dir)
                selected_path.mkdir(parents=True, exist_ok=True)
            except ValueError:
                raise BackupDriveSetupError(
                    'In fake mode, choose an existing folder on this machine or a path inside .dev-data.'
                )
        if not selected_path.is_dir():
            raise BackupDriveSetupError('Source path must be a directory.')

        uuid = 'FAKE-UUID-0001'
        usb_id = 'FAKE:0001'
        selected_path_str = str(selected_path)
        fstab_backup = None
        share_backup = None
        config_updated = False

        try:
            fstab_backup = update_managed_fstab(uuid, selected_path_str, bool(auto_mount), runtime=runtime)
            _reload_systemd_mount_units(runtime=runtime)

            backup_share = smb_manager.get_managed_share('backup')

            if backup_share and backup_share.get('path') != selected_path_str:
                share_backup = backup_share
                _sync_backup_share_path(smb_manager, selected_path_str)

            config_updated = True
            config_manager.set_value('backup', 'mount_point', selected_path_str)
            config_manager.set_value('backup', 'uuid', uuid)
            config_manager.set_value('backup', 'usb_id', usb_id)
            fake_state.set_mount(True, mount_point=selected_path_str, drive=partition or '/dev/fakebackup1')
            return {
                'message': 'Successfully selected local backup source at {}'.format(selected_path),
                'uuid': uuid,
                'usb_id': usb_id,
                'mount_point': selected_path_str,
            }
        except Exception:
            if fstab_backup:
                restore_fstab_backup(fstab_backup, runtime=runtime)
                _reload_systemd_mount_units(runtime=runtime)
            if share_backup:
                try:
                    smb_manager.update_share(
                        old_name='backup',
                        new_name='backup',
                        path=share_backup.get('path', previous_mount_point),
                        writable=share_backup.get('writable', True),
                        comment=share_backup.get('comment', ''),
                        valid_users=share_backup.get('valid_users', []),
                    )
                except Exception as share_exc:
                    LOGGER.error('Failed to restore fake backup share after drive setup error: %s', share_exc)
            if config_updated:
                try:
                    config_manager.set_value('backup', 'mount_point', previous_mount_point)
                    config_manager.set_value('backup', 'uuid', previous_uuid)
                    config_manager.set_value('backup', 'usb_id', previous_usb_id)
                except Exception as config_exc:
                    LOGGER.error('Failed to restore fake backup config after drive setup error: %s', config_exc)
            raise

    if not partition:
        raise BackupDriveSetupError('No partition selected.')

    # This flow is partition-oriented by design. If the user selected /dev/sdb1,
    # we should not block on or touch unrelated devices on the same disk.
    mounted_partition = _get_mount_for_partition(partition)
    if mounted_partition:
        raise BackupDriveSetupError(
            'The selected partition is already mounted at {}. Unmount it first before rerunning drive setup.'.format(
                mounted_partition['mount_point']
            )
        )

    uuid = get_drive_uuid(partition)
    usb_id = get_drive_usb_id(partition)
    filesystem_type = _get_partition_filesystem_type(partition)
    if not _is_ntfs_filesystem(filesystem_type):
        raise BackupDriveSetupError('The selected partition must be formatted as NTFS.')

    os.makedirs(mount_point, exist_ok=True)

    mounted = False
    fstab_backup = None
    share_backup = None
    config_updated = False

    try:
        fstab_backup = update_managed_fstab(uuid, mount_point, bool(auto_mount), runtime=runtime)
        _reload_systemd_mount_units(runtime=runtime)

        mount_result = subprocess.run(
            ['ntfs-3g', partition, mount_point, '-o', 'rw,uid=1000,gid=1000'],
            capture_output=True,
            text=True,
        )
        if mount_result.returncode != 0:
            error_msg = mount_result.stderr.strip() if mount_result.stderr else 'Unknown error occurred'
            raise BackupDriveSetupError('Error mounting drive: {}'.format(error_msg))
        mounted = True

        backup_share = smb_manager.get_managed_share('backup')

        if backup_share and backup_share.get('path') != mount_point:
            share_backup = backup_share
            _sync_backup_share_path(smb_manager, mount_point)

        config_updated = True
        config_manager.set_value('backup', 'mount_point', mount_point)
        config_manager.set_value('backup', 'uuid', uuid)
        config_manager.set_value('backup', 'usb_id', usb_id)

        return {
            'message': 'Successfully configured {} at {}'.format(partition, mount_point),
            'uuid': uuid,
            'usb_id': usb_id,
            'mount_point': mount_point,
        }
    except Exception:
        if mounted:
            subprocess.run(['umount', partition], check=False)
        if fstab_backup:
            restore_fstab_backup(fstab_backup, runtime=runtime)
            _reload_systemd_mount_units(runtime=runtime)
        if share_backup:
            try:
                smb_manager.update_managed_share(
                    old_name='backup',
                    new_name='backup',
                    path=share_backup.get('path', previous_mount_point),
                    writable=share_backup.get('writable', True),
                    comment=share_backup.get('comment', ''),
                    valid_users=share_backup.get('valid_users', []),
                )
            except Exception as share_exc:
                LOGGER.error('Failed to restore backup share after drive setup error: %s', share_exc)
        if config_updated:
            try:
                config_manager.set_value('backup', 'mount_point', previous_mount_point)
                config_manager.set_value('backup', 'uuid', previous_uuid)
                config_manager.set_value('backup', 'usb_id', previous_usb_id)
            except Exception as config_exc:
                LOGGER.error('Failed to restore backup config after drive setup error: %s', config_exc)
        raise
