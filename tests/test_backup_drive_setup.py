import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from simple_safer_server.services import backup_drive_setup


class FakeBackupDriveCommandAdapter:
    def __init__(self):
        self.unmount_results = []
        self.mount_ntfs_result = SimpleNamespace(returncode=0, stderr='', stdout='')
        self.unmounted_partitions = []
        self.mounted_ntfs = []
        self.cleanup_unmounted = []
        self.lsblk_devices_json_result = SimpleNamespace(
            returncode=0,
            stderr='',
            stdout='{"blockdevices":[]}',
        )
        self.current_mounts_result = SimpleNamespace(returncode=0, stderr='', stdout='')

    def lsblk_devices_json(self):
        return self.lsblk_devices_json_result

    def current_mounts(self):
        return self.current_mounts_result

    def unmount_partition(self, device):
        self.unmounted_partitions.append(device)
        if self.unmount_results:
            return self.unmount_results.pop(0)
        return SimpleNamespace(returncode=0, stderr='', stdout='')

    def mount_ntfs(self, partition, mount_point):
        self.mounted_ntfs.append((partition, mount_point))
        return self.mount_ntfs_result

    def cleanup_unmount(self, device):
        self.cleanup_unmounted.append(device)


class BackupDriveSetupTests(unittest.TestCase):
    def test_backup_share_update_snapshot_ignores_later_share_mutation(self):
        share = {
            'path': '/media/backup',
            'writable': True,
            'comment': 'Managed backup share',
            'valid_users': ['admin'],
        }

        snapshot = backup_drive_setup._BackupShareUpdate.from_share(share, share['path'])
        share['path'] = '/tmp/changed'
        share['valid_users'].append('backup-admin')

        smb_manager = MagicMock()
        snapshot.apply(smb_manager)

        self.assertEqual(
            smb_manager.update_managed_share.call_args[1],
            {
                'old_name': 'backup',
                'new_name': 'backup',
                'path': '/media/backup',
                'writable': True,
                'comment': 'Managed backup share',
                'valid_users': ['admin'],
            },
        )

    @patch(
        'simple_safer_server.services.backup_drive_setup._get_system_drive_path',
        return_value='/dev/sda',
    )
    @patch('simple_safer_server.services.backup_drive_setup._load_lsblk_devices')
    def test_list_available_drives_keeps_fuseblk_partition_when_blkid_confirms_ntfs(
        self,
        mock_load_lsblk_devices,
        _mock_get_system_drive_path,
    ):
        mock_load_lsblk_devices.return_value = [
            {
                'type': 'disk',
                'path': '/dev/sdb',
                'model': 'Backup Disk',
                'size': '1T',
                'children': [
                    {
                        'path': '/dev/sdb1',
                        'fstype': 'fuseblk',
                        'label': 'Backup',
                        'size': '1T',
                        'mountpoint': '/media/backup',
                    }
                ],
            }
        ]

        with patch(
            'simple_safer_server.services.backup_drive_setup._get_blkid_filesystem_type',
            return_value='ntfs',
        ) as mock_blkid:
            drives = backup_drive_setup.list_available_drives(
                runtime=SimpleNamespace(is_fake=False),
                ntfs_only=True,
            )

        self.assertEqual(len(drives), 1)
        self.assertEqual(drives[0]['partitions'][0]['path'], '/dev/sdb1')
        self.assertEqual(drives[0]['partitions'][0]['type'], 'ntfs')
        mock_blkid.assert_called_once_with('/dev/sdb1')

    @patch(
        'simple_safer_server.services.backup_drive_setup._get_system_drive_path',
        return_value='/dev/sda',
    )
    @patch('simple_safer_server.services.backup_drive_setup._load_lsblk_devices')
    def test_list_available_drives_normalizes_ntfs3_partition_type_for_ntfs_picker(
        self,
        mock_load_lsblk_devices,
        _mock_get_system_drive_path,
    ):
        mock_load_lsblk_devices.return_value = [
            {
                'type': 'disk',
                'path': '/dev/sdb',
                'model': 'Backup Disk',
                'size': '1T',
                'children': [
                    {
                        'path': '/dev/sdb1',
                        'fstype': 'ntfs3',
                        'label': 'Backup',
                        'size': '1T',
                        'mountpoint': '',
                    }
                ],
            }
        ]

        drives = backup_drive_setup.list_available_drives(
            runtime=SimpleNamespace(is_fake=False),
            ntfs_only=True,
        )

        self.assertEqual(len(drives), 1)
        self.assertEqual(drives[0]['partitions'][0]['type'], 'ntfs')

    @patch(
        'simple_safer_server.services.backup_drive_setup._get_system_drive_path',
        return_value='/dev/sda',
    )
    @patch('simple_safer_server.services.backup_drive_setup._load_lsblk_devices')
    def test_list_available_drives_marks_usb_transport_as_usb_drive(
        self,
        mock_load_lsblk_devices,
        _mock_get_system_drive_path,
    ):
        mock_load_lsblk_devices.return_value = [
            {
                'type': 'disk',
                'path': '/dev/sdb',
                'model': 'USB Backup Disk',
                'size': '1T',
                'tran': 'usb',
                'rm': False,
                'hotplug': False,
                'children': [],
            }
        ]

        drives = backup_drive_setup.list_available_drives(
            runtime=SimpleNamespace(is_fake=False),
            ntfs_only=False,
        )

        self.assertEqual(len(drives), 1)
        self.assertEqual(drives[0]['type'], 'usb')
        self.assertEqual(drives[0]['device_type'], 'disk')

    @patch(
        'simple_safer_server.services.backup_drive_setup._get_system_drive_path',
        return_value='/dev/sda',
    )
    @patch('simple_safer_server.services.backup_drive_setup._load_lsblk_devices')
    def test_list_available_drives_marks_hotplug_disk_as_removable_when_transport_is_missing(
        self,
        mock_load_lsblk_devices,
        _mock_get_system_drive_path,
    ):
        mock_load_lsblk_devices.return_value = [
            {
                'type': 'disk',
                'path': '/dev/sdb',
                'model': 'Card Reader',
                'size': '128G',
                'tran': '',
                'rm': '1',
                'hotplug': '1',
                'children': [],
            }
        ]

        drives = backup_drive_setup.list_available_drives(
            runtime=SimpleNamespace(is_fake=False),
            ntfs_only=False,
        )

        self.assertEqual(len(drives), 1)
        self.assertEqual(drives[0]['type'], 'removable')

    @patch(
        'simple_safer_server.services.backup_drive_setup._get_system_drive_path',
        return_value='/dev/sda',
    )
    @patch('simple_safer_server.services.backup_drive_setup._load_lsblk_devices')
    def test_list_available_drives_skips_fuseblk_partition_when_blkid_is_not_ntfs(
        self,
        mock_load_lsblk_devices,
        _mock_get_system_drive_path,
    ):
        mock_load_lsblk_devices.return_value = [
            {
                'type': 'disk',
                'path': '/dev/sdb',
                'model': 'Backup Disk',
                'size': '1T',
                'children': [
                    {
                        'path': '/dev/sdb1',
                        'fstype': 'fuseblk',
                        'label': 'Something Else',
                        'size': '1T',
                        'mountpoint': '/media/other',
                    }
                ],
            }
        ]

        with patch(
            'simple_safer_server.services.backup_drive_setup._get_blkid_filesystem_type',
            return_value='exfat',
        ) as mock_blkid:
            drives = backup_drive_setup.list_available_drives(
                runtime=SimpleNamespace(is_fake=False),
                ntfs_only=True,
            )

        self.assertEqual(drives, [])
        mock_blkid.assert_called_once_with('/dev/sdb1')

    def test_get_mounted_partitions_for_disk_matches_child_partitions(self):
        blockdevices = [
            {
                'type': 'disk',
                'path': '/dev/sdb',
                'children': [
                    {'path': '/dev/sdb1'},
                    {'path': '/dev/sdb2'},
                ],
            }
        ]
        mounts = [
            {'device': '/dev/sdb1', 'mount_point': '/media/one'},
            {'device': '/dev/sdc1', 'mount_point': '/media/other'},
        ]

        mounted = backup_drive_setup._get_mounted_partitions_for_disk(
            '/dev/sdb',
            blockdevices=blockdevices,
            mounts=mounts,
        )

        self.assertEqual(
            mounted,
            [{'device': '/dev/sdb1', 'mount_point': '/media/one'}],
        )

    def test_get_mounted_partitions_for_disk_uses_injected_command_adapter_for_discovery(self):
        command_adapter = FakeBackupDriveCommandAdapter()
        command_adapter.lsblk_devices_json_result = SimpleNamespace(
            returncode=0,
            stderr='',
            stdout=(
                '{"blockdevices":[{"type":"disk","path":"/dev/sdb",'
                '"children":[{"path":"/dev/sdb1"}]}]}'
            ),
        )
        command_adapter.current_mounts_result = SimpleNamespace(
            returncode=0,
            stderr='',
            stdout='/dev/sdb1 on /media/backup type ntfs3 (rw)\n',
        )

        mounted = backup_drive_setup._get_mounted_partitions_for_disk(
            '/dev/sdb',
            command_adapter=command_adapter,
        )

        self.assertEqual(
            mounted,
            [{'device': '/dev/sdb1', 'mount_point': '/media/backup'}],
        )

    @patch(
        'simple_safer_server.services.backup_drive_setup._get_system_drive_path',
        return_value='/dev/sda',
    )
    @patch('simple_safer_server.services.backup_drive_setup._load_lsblk_devices')
    def test_list_available_drives_keeps_blank_disk_for_broad_format_scan(
        self,
        mock_load_lsblk_devices,
        _mock_get_system_drive_path,
    ):
        mock_load_lsblk_devices.return_value = [
            {
                'type': 'disk',
                'path': '/dev/sdb',
                'model': 'Blank Disk',
                'size': '2T',
                'children': [],
            }
        ]

        drives = backup_drive_setup.list_available_drives(
            runtime=SimpleNamespace(is_fake=False),
            ntfs_only=False,
        )

        self.assertEqual(len(drives), 1)
        self.assertEqual(drives[0]['path'], '/dev/sdb')
        self.assertEqual(drives[0]['partitions'], [])

    def test_get_mount_for_partition_requires_exact_match(self):
        mounts = [
            {'device': '/dev/sdb11', 'mount_point': '/media/eleven'},
            {'device': '/dev/sdb1', 'mount_point': '/media/one'},
        ]

        mount = backup_drive_setup._get_mount_for_partition('/dev/sdb1', mounts=mounts)

        self.assertEqual(mount, {'device': '/dev/sdb1', 'mount_point': '/media/one'})

    @patch('simple_safer_server.services.backup_drive_setup._get_mounted_partitions_for_disk')
    def test_unmount_disk_partitions_unmounts_all_members(self, mock_get_mounted):
        runtime = SimpleNamespace(is_fake=False)
        command_adapter = FakeBackupDriveCommandAdapter()
        mock_get_mounted.return_value = [
            {'device': '/dev/sdb1', 'mount_point': '/media/one'},
            {'device': '/dev/sdb2', 'mount_point': '/media/two'},
        ]

        message = backup_drive_setup.unmount_disk_partitions(
            '/dev/sdb', runtime=runtime, command_adapter=command_adapter
        )

        self.assertEqual(message, 'Successfully unmounted 2 partition(s).')
        self.assertEqual(command_adapter.unmounted_partitions, ['/dev/sdb1', '/dev/sdb2'])
        mock_get_mounted.assert_called_once_with('/dev/sdb', command_adapter=command_adapter)

    @patch('simple_safer_server.services.backup_drive_setup._get_mount_for_partition')
    def test_unmount_selected_partition_only_unmounts_exact_partition(self, mock_get_mount):
        runtime = SimpleNamespace(is_fake=False)
        command_adapter = FakeBackupDriveCommandAdapter()
        mock_get_mount.return_value = {'device': '/dev/sdb1', 'mount_point': '/media/one'}

        message = backup_drive_setup.unmount_selected_partition(
            '/dev/sdb1', runtime=runtime, command_adapter=command_adapter
        )

        self.assertEqual(message, 'Successfully unmounted /dev/sdb1.')
        self.assertEqual(command_adapter.unmounted_partitions, ['/dev/sdb1'])
        mock_get_mount.assert_called_once_with('/dev/sdb1', command_adapter=command_adapter)

    @patch('simple_safer_server.services.backup_drive_setup.os.makedirs')
    @patch('simple_safer_server.services.backup_drive_setup._reload_systemd_mount_units')
    @patch('simple_safer_server.services.backup_drive_setup.update_managed_fstab')
    @patch('simple_safer_server.services.backup_drive_setup._get_partition_filesystem_type')
    @patch('simple_safer_server.services.backup_drive_setup.get_drive_usb_id')
    @patch('simple_safer_server.services.backup_drive_setup.get_drive_uuid')
    @patch('simple_safer_server.services.backup_drive_setup._get_mount_for_partition')
    def test_apply_backup_drive_configuration_checks_only_selected_partition_mount(
        self,
        mock_get_mount,
        mock_get_uuid,
        mock_get_usb_id,
        mock_get_fstype,
        mock_update_fstab,
        mock_reload_mount_units,
        mock_makedirs,
    ):
        runtime = SimpleNamespace(is_fake=False, default_mount_point='/media/backup')
        command_adapter = FakeBackupDriveCommandAdapter()
        config_manager = MagicMock()
        config_manager.get_value.side_effect = ['/media/backup', '', '']
        smb_manager = MagicMock()
        smb_manager.get_managed_share.return_value = None

        mock_get_mount.return_value = None
        mock_get_uuid.return_value = 'UUID-1'
        mock_get_usb_id.return_value = '1234:5678'
        mock_get_fstype.return_value = 'ntfs'
        mock_update_fstab.return_value = None

        result = backup_drive_setup.apply_backup_drive_configuration(
            '/dev/sdb1',
            '/media/backup',
            True,
            config_manager,
            smb_manager,
            runtime=runtime,
            command_adapter=command_adapter,
        )

        self.assertEqual(result['uuid'], 'UUID-1')
        mock_get_mount.assert_called_once_with('/dev/sdb1', command_adapter=command_adapter)
        mock_reload_mount_units.assert_called_once_with(runtime=runtime)
        self.assertEqual(command_adapter.mounted_ntfs, [('/dev/sdb1', '/media/backup')])

    @patch('simple_safer_server.services.backup_drive_setup.restore_fstab_backup')
    @patch('simple_safer_server.services.backup_drive_setup.os.makedirs')
    @patch('simple_safer_server.services.backup_drive_setup._reload_systemd_mount_units')
    @patch('simple_safer_server.services.backup_drive_setup.update_managed_fstab')
    @patch('simple_safer_server.services.backup_drive_setup._get_partition_filesystem_type')
    @patch('simple_safer_server.services.backup_drive_setup.get_drive_usb_id')
    @patch('simple_safer_server.services.backup_drive_setup.get_drive_uuid')
    @patch('simple_safer_server.services.backup_drive_setup._get_mount_for_partition')
    def test_apply_backup_drive_configuration_restores_and_reloads_fstab_after_mount_failure(
        self,
        mock_get_mount,
        mock_get_uuid,
        mock_get_usb_id,
        mock_get_fstype,
        mock_update_fstab,
        mock_reload_mount_units,
        mock_makedirs,
        mock_restore_fstab_backup,
    ):
        runtime = SimpleNamespace(is_fake=False, default_mount_point='/media/backup')
        command_adapter = FakeBackupDriveCommandAdapter()
        config_manager = MagicMock()
        config_manager.get_value.side_effect = ['/media/backup', 'OLD-UUID', '1234:5678']
        smb_manager = MagicMock()
        smb_manager.get_managed_share.return_value = None

        mock_get_mount.return_value = None
        mock_get_uuid.return_value = 'UUID-1'
        mock_get_usb_id.return_value = '1234:5678'
        mock_get_fstype.return_value = 'ntfs'
        mock_update_fstab.return_value = '/tmp/fstab.backup'
        command_adapter.mount_ntfs_result = SimpleNamespace(returncode=1, stderr='busy', stdout='')

        with self.assertRaisesRegex(
            backup_drive_setup.BackupDriveSetupError, 'Error mounting drive: busy'
        ):
            backup_drive_setup.apply_backup_drive_configuration(
                '/dev/sdb1',
                '/media/backup',
                True,
                config_manager,
                smb_manager,
                runtime=runtime,
                command_adapter=command_adapter,
            )

        mock_restore_fstab_backup.assert_called_once_with('/tmp/fstab.backup', runtime=runtime)
        self.assertEqual(mock_reload_mount_units.call_count, 2)

    @patch('simple_safer_server.services.backup_drive_setup.restore_fstab_backup')
    @patch('simple_safer_server.services.backup_drive_setup.os.makedirs')
    @patch('simple_safer_server.services.backup_drive_setup._reload_systemd_mount_units')
    @patch('simple_safer_server.services.backup_drive_setup.update_managed_fstab')
    @patch('simple_safer_server.services.backup_drive_setup._get_partition_filesystem_type')
    @patch('simple_safer_server.services.backup_drive_setup.get_drive_usb_id')
    @patch('simple_safer_server.services.backup_drive_setup.get_drive_uuid')
    @patch('simple_safer_server.services.backup_drive_setup._get_mount_for_partition')
    def test_apply_backup_drive_configuration_restores_fstab_when_daemon_reload_fails(
        self,
        mock_get_mount,
        mock_get_uuid,
        mock_get_usb_id,
        mock_get_fstype,
        mock_update_fstab,
        mock_reload_mount_units,
        mock_makedirs,
        mock_restore_fstab_backup,
    ):
        runtime = SimpleNamespace(is_fake=False, default_mount_point='/media/backup')
        command_adapter = FakeBackupDriveCommandAdapter()
        config_manager = MagicMock()
        config_manager.get_value.side_effect = ['/media/backup', 'OLD-UUID', '1234:5678']
        smb_manager = MagicMock()
        smb_manager.get_managed_share.return_value = None

        mock_get_mount.return_value = None
        mock_get_uuid.return_value = 'UUID-1'
        mock_get_usb_id.return_value = '1234:5678'
        mock_get_fstype.return_value = 'ntfs'
        mock_update_fstab.return_value = '/tmp/fstab.backup'
        mock_reload_mount_units.side_effect = [
            backup_drive_setup.BackupDriveSetupError(
                'Failed to reload systemd after updating /etc/fstab: bad reload'
            ),
            None,
        ]

        with self.assertRaisesRegex(
            backup_drive_setup.BackupDriveSetupError,
            'Failed to reload systemd after updating /etc/fstab: bad reload',
        ):
            backup_drive_setup.apply_backup_drive_configuration(
                '/dev/sdb1',
                '/media/backup',
                True,
                config_manager,
                smb_manager,
                runtime=runtime,
                command_adapter=command_adapter,
            )

        mock_restore_fstab_backup.assert_called_once_with('/tmp/fstab.backup', runtime=runtime)
        self.assertEqual(mock_reload_mount_units.call_count, 2)
        self.assertEqual(command_adapter.mounted_ntfs, [])

    @patch('simple_safer_server.services.backup_drive_setup.get_fake_state')
    @patch('simple_safer_server.services.backup_drive_setup.restore_fstab_backup')
    @patch('simple_safer_server.services.backup_drive_setup._reload_systemd_mount_units')
    @patch('simple_safer_server.services.backup_drive_setup.update_managed_fstab')
    def test_fake_mode_rollback_restores_share_via_update_managed_share(
        self,
        mock_update_fstab,
        mock_reload_mount_units,
        mock_restore_fstab_backup,
        mock_get_fake_state,
    ):
        with tempfile.TemporaryDirectory() as tempdir:
            data_dir = Path(tempdir)
            selected_path = data_dir / 'selected-backup'
            selected_path.mkdir()

            runtime = SimpleNamespace(
                is_fake=True,
                data_dir=data_dir,
                default_mount_point='/media/backup',
            )
            fake_state = MagicMock()
            mock_get_fake_state.return_value = fake_state
            mock_update_fstab.return_value = '/tmp/fstab.backup'

            config_manager = MagicMock()
            config_manager.get_value.side_effect = ['/media/backup', 'OLD-UUID', 'OLD-USB']
            config_manager.set_value.side_effect = [None, None, RuntimeError('boom')]

            smb_manager = MagicMock()
            smb_manager.get_managed_share.return_value = {
                'name': 'backup',
                'path': '/media/backup',
                'writable': True,
                'comment': 'Managed backup share',
                'valid_users': ['admin'],
            }

            with self.assertRaisesRegex(RuntimeError, 'boom'):
                backup_drive_setup.apply_backup_drive_configuration(
                    '/dev/fakebackup1',
                    str(selected_path),
                    True,
                    config_manager,
                    smb_manager,
                    runtime=runtime,
                )

        self.assertGreaterEqual(smb_manager.update_managed_share.call_count, 2)
        self.assertEqual(
            smb_manager.update_managed_share.call_args_list[-1][1],
            {
                'old_name': 'backup',
                'new_name': 'backup',
                'path': '/media/backup',
                'writable': True,
                'comment': 'Managed backup share',
                'valid_users': ['admin'],
            },
        )

    @patch('simple_safer_server.services.backup_drive_setup.get_fake_state')
    @patch('simple_safer_server.services.backup_drive_setup.restore_fstab_backup')
    @patch('simple_safer_server.services.backup_drive_setup._reload_systemd_mount_units')
    @patch('simple_safer_server.services.backup_drive_setup.update_managed_fstab')
    def test_fake_mode_rollback_uses_share_snapshot_when_share_record_mutates(
        self,
        mock_update_fstab,
        mock_reload_mount_units,
        mock_restore_fstab_backup,
        mock_get_fake_state,
    ):
        del mock_reload_mount_units
        del mock_restore_fstab_backup

        with tempfile.TemporaryDirectory() as tempdir:
            data_dir = Path(tempdir)
            selected_path = data_dir / 'selected-backup'
            selected_path.mkdir()

            runtime = SimpleNamespace(
                is_fake=True,
                data_dir=data_dir,
                default_mount_point='/media/backup',
            )
            fake_state = MagicMock()
            mock_get_fake_state.return_value = fake_state
            mock_update_fstab.return_value = '/tmp/fstab.backup'

            config_manager = MagicMock()
            config_manager.get_value.side_effect = ['/media/backup', 'OLD-UUID', 'OLD-USB']
            config_manager.set_value.side_effect = [None, None, RuntimeError('boom')]

            managed_share = {
                'name': 'backup',
                'path': '/media/backup',
                'writable': True,
                'comment': 'Managed backup share',
                'valid_users': ['admin'],
            }
            smb_manager = MagicMock()
            smb_manager.get_managed_share.return_value = managed_share

            def mutate_share_record(**kwargs):
                # Simulate an SMB manager implementation that rewrites the live
                # share record in place after the new path is applied.
                if kwargs['path'] == str(selected_path):
                    managed_share['path'] = kwargs['path']
                    managed_share['valid_users'].append('backup-admin')

            smb_manager.update_managed_share.side_effect = mutate_share_record

            with self.assertRaisesRegex(RuntimeError, 'boom'):
                backup_drive_setup.apply_backup_drive_configuration(
                    '/dev/fakebackup1',
                    str(selected_path),
                    True,
                    config_manager,
                    smb_manager,
                    runtime=runtime,
                )

        self.assertEqual(
            smb_manager.update_managed_share.call_args_list[-1][1],
            {
                'old_name': 'backup',
                'new_name': 'backup',
                'path': '/media/backup',
                'writable': True,
                'comment': 'Managed backup share',
                'valid_users': ['admin'],
            },
        )


if __name__ == '__main__':
    unittest.main()
