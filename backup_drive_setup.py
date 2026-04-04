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


def _mount_belongs_to_drive(selected_drive, mounted_device):
    selected_drive = (selected_drive or '').strip()
    mounted_device = (mounted_device or '').strip()
    if not selected_drive or not mounted_device:
        return False
    # The rerun flow selects a partition path, not a whole disk. Match the
    # mounted source exactly so names like /dev/sdb1 never catch /dev/sdb11.
    return os.path.realpath(mounted_device) == os.path.realpath(selected_drive)


def _get_mounted_partitions_for_drive(drive):
    mount_check = subprocess.run(['mount'], capture_output=True, text=True)
    mounted_partitions = []
    for line in mount_check.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and _mount_belongs_to_drive(drive, parts[0]):
            mounted_partitions.append({'device': parts[0], 'mount_point': parts[2]})
    return mounted_partitions


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

    lsblk_result = subprocess.run(
        ['lsblk', '-J', '-o', 'NAME,PATH,FSTYPE,LABEL,SIZE,MODEL,MOUNTPOINT,TYPE'],
        capture_output=True,
        text=True,
    )
    if lsblk_result.returncode != 0:
        raise BackupDriveSetupError('Failed to list drives.')

    try:
        lsblk_data = json.loads(lsblk_result.stdout)
    except Exception as exc:
        raise BackupDriveSetupError('Failed to parse drive list.') from exc

    root_mount = subprocess.run(['findmnt', '-n', '-o', 'SOURCE', '/'], capture_output=True, text=True)
    system_drive = root_mount.stdout.strip() if root_mount.returncode == 0 else None

    drives = []
    for block in lsblk_data.get('blockdevices', []):
        if block.get('type') != 'disk':
            continue

        disk_path = block.get('path')
        if not disk_path:
            continue

        if system_drive and system_drive.startswith(disk_path):
            continue

        partitions = []
        for child in block.get('children', []) or []:
            child_path = child.get('path')
            if not child_path:
                continue
            filesystem_type = child.get('fstype') or ''
            if ntfs_only and not _is_ntfs_filesystem(filesystem_type):
                continue
            partitions.append({
                'path': child_path,
                'type': filesystem_type or child.get('type') or 'unknown',
                'label': child.get('label') or '',
                'size': child.get('size') or '',
                'mountpoint': child.get('mountpoint') or '',
            })

        block_filesystem_type = block.get('fstype') or ''
        if not partitions and _is_ntfs_filesystem(block_filesystem_type):
            partitions.append({
                'path': disk_path,
                'type': block_filesystem_type or block.get('type') or 'unknown',
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
            'type': block.get('type') or 'unknown',
            'partitions': partitions,
        })

    return drives


def unmount_selected_drive(drive, runtime=None):
    runtime = runtime or get_runtime()
    fake_state = get_fake_state() if runtime.is_fake else None

    if runtime.is_fake:
        fake_state.set_mount(False)
        return 'Fake backup source disconnected.'

    if not drive:
        raise BackupDriveSetupError('No drive selected.')

    mounted_partitions = _get_mounted_partitions_for_drive(drive)

    if not mounted_partitions:
        raise BackupDriveSetupError('The selected drive is not currently mounted.')

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


def _sync_backup_share_path(smb_manager, new_path):
    for share in smb_manager.get_shares():
        if share.get('name') != 'backup':
            continue
        smb_manager.update_share(
            old_name='backup',
            new_name='backup',
            path=new_path,
            writable=share.get('writable', True),
            comment=share.get('comment', ''),
            valid_users=share.get('valid_users', []),
        )
        return True
    return False


def apply_backup_drive_configuration(drive, mount_point, auto_mount, config_manager, smb_manager, runtime=None):
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

            backup_share = None
            for share in smb_manager.get_shares():
                if share.get('name') == 'backup':
                    backup_share = share
                    break

            if backup_share and backup_share.get('path') != selected_path_str:
                share_backup = backup_share
                _sync_backup_share_path(smb_manager, selected_path_str)

            config_manager.set_value('backup', 'mount_point', selected_path_str)
            config_manager.set_value('backup', 'uuid', uuid)
            config_manager.set_value('backup', 'usb_id', usb_id)
            config_updated = True
            fake_state.set_mount(True, mount_point=selected_path_str, drive=drive or '/dev/fakebackup1')
            return {
                'message': 'Successfully selected local backup source at {}'.format(selected_path),
                'uuid': uuid,
                'usb_id': usb_id,
                'mount_point': selected_path_str,
            }
        except Exception:
            if fstab_backup:
                restore_fstab_backup(fstab_backup, runtime=runtime)
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

    if not drive:
        raise BackupDriveSetupError('No drive selected.')

    mounted_partitions = _get_mounted_partitions_for_drive(drive)
    if mounted_partitions:
        raise BackupDriveSetupError(
            'The selected drive is already mounted at {}. Unmount it first before rerunning drive setup.'.format(
                mounted_partitions[0]['mount_point']
            )
        )

    uuid = get_drive_uuid(drive)
    usb_id = get_drive_usb_id(drive)
    filesystem_type = _get_partition_filesystem_type(drive)
    if not _is_ntfs_filesystem(filesystem_type):
        raise BackupDriveSetupError('The selected drive must be formatted as NTFS.')

    os.makedirs(mount_point, exist_ok=True)

    mounted = False
    fstab_backup = None
    share_backup = None
    config_updated = False

    try:
        fstab_backup = update_managed_fstab(uuid, mount_point, bool(auto_mount), runtime=runtime)

        mount_result = subprocess.run(
            ['ntfs-3g', drive, mount_point, '-o', 'rw,uid=1000,gid=1000'],
            capture_output=True,
            text=True,
        )
        if mount_result.returncode != 0:
            error_msg = mount_result.stderr.strip() if mount_result.stderr else 'Unknown error occurred'
            raise BackupDriveSetupError('Error mounting drive: {}'.format(error_msg))
        mounted = True

        backup_share = None
        for share in smb_manager.get_shares():
            if share.get('name') == 'backup':
                backup_share = share
                break

        if backup_share and backup_share.get('path') != mount_point:
            share_backup = backup_share
            _sync_backup_share_path(smb_manager, mount_point)

        config_manager.set_value('backup', 'mount_point', mount_point)
        config_manager.set_value('backup', 'uuid', uuid)
        config_manager.set_value('backup', 'usb_id', usb_id)
        config_updated = True

        return {
            'message': 'Successfully configured {} at {}'.format(drive, mount_point),
            'uuid': uuid,
            'usb_id': usb_id,
            'mount_point': mount_point,
        }
    except Exception:
        if mounted:
            subprocess.run(['umount', drive], check=False)
        if fstab_backup:
            restore_fstab_backup(fstab_backup, runtime=runtime)
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
                LOGGER.error('Failed to restore backup share after drive setup error: %s', share_exc)
        if config_updated:
            try:
                config_manager.set_value('backup', 'mount_point', previous_mount_point)
                config_manager.set_value('backup', 'uuid', previous_uuid)
                config_manager.set_value('backup', 'usb_id', previous_usb_id)
            except Exception as config_exc:
                LOGGER.error('Failed to restore backup config after drive setup error: %s', config_exc)
        raise
