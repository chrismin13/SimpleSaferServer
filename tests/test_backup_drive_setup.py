import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import backup_drive_setup


class BackupDriveSetupTests(unittest.TestCase):
    @patch('backup_drive_setup._get_system_drive_path', return_value='/dev/sda')
    @patch('backup_drive_setup._load_lsblk_devices')
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

        with patch('backup_drive_setup._get_blkid_filesystem_type', return_value='ntfs') as mock_blkid:
            drives = backup_drive_setup.list_available_drives(
                runtime=SimpleNamespace(is_fake=False),
                ntfs_only=True,
            )

        self.assertEqual(len(drives), 1)
        self.assertEqual(drives[0]['partitions'][0]['path'], '/dev/sdb1')
        self.assertEqual(drives[0]['partitions'][0]['type'], 'ntfs')
        mock_blkid.assert_called_once_with('/dev/sdb1')

    @patch('backup_drive_setup._get_system_drive_path', return_value='/dev/sda')
    @patch('backup_drive_setup._load_lsblk_devices')
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

    @patch('backup_drive_setup._get_system_drive_path', return_value='/dev/sda')
    @patch('backup_drive_setup._load_lsblk_devices')
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

    @patch('backup_drive_setup._get_system_drive_path', return_value='/dev/sda')
    @patch('backup_drive_setup._load_lsblk_devices')
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

    @patch('backup_drive_setup._get_system_drive_path', return_value='/dev/sda')
    @patch('backup_drive_setup._load_lsblk_devices')
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

        with patch('backup_drive_setup._get_blkid_filesystem_type', return_value='exfat') as mock_blkid:
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

    @patch('backup_drive_setup._get_system_drive_path', return_value='/dev/sda')
    @patch('backup_drive_setup._load_lsblk_devices')
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

    @patch('backup_drive_setup.subprocess.run')
    @patch('backup_drive_setup._get_mounted_partitions_for_disk')
    def test_unmount_disk_partitions_unmounts_all_members(self, mock_get_mounted, mock_run):
        runtime = SimpleNamespace(is_fake=False)
        mock_get_mounted.return_value = [
            {'device': '/dev/sdb1', 'mount_point': '/media/one'},
            {'device': '/dev/sdb2', 'mount_point': '/media/two'},
        ]
        mock_run.return_value = SimpleNamespace(returncode=0, stderr='')

        message = backup_drive_setup.unmount_disk_partitions('/dev/sdb', runtime=runtime)

        self.assertEqual(message, 'Successfully unmounted 2 partition(s).')
        self.assertEqual(
            mock_run.call_args_list,
            [
                unittest.mock.call(['umount', '/dev/sdb1'], capture_output=True, text=True),
                unittest.mock.call(['umount', '/dev/sdb2'], capture_output=True, text=True),
            ],
        )

    @patch('backup_drive_setup.subprocess.run')
    @patch('backup_drive_setup._get_mount_for_partition')
    def test_unmount_selected_partition_only_unmounts_exact_partition(self, mock_get_mount, mock_run):
        runtime = SimpleNamespace(is_fake=False)
        mock_get_mount.return_value = {'device': '/dev/sdb1', 'mount_point': '/media/one'}
        mock_run.return_value = SimpleNamespace(returncode=0, stderr='')

        message = backup_drive_setup.unmount_selected_partition('/dev/sdb1', runtime=runtime)

        self.assertEqual(message, 'Successfully unmounted /dev/sdb1.')
        mock_run.assert_called_once_with(['umount', '/dev/sdb1'], capture_output=True, text=True)

    @patch('backup_drive_setup.subprocess.run')
    @patch('backup_drive_setup.os.makedirs')
    @patch('backup_drive_setup._reload_systemd_mount_units')
    @patch('backup_drive_setup.update_managed_fstab')
    @patch('backup_drive_setup._get_partition_filesystem_type')
    @patch('backup_drive_setup.get_drive_usb_id')
    @patch('backup_drive_setup.get_drive_uuid')
    @patch('backup_drive_setup._get_mount_for_partition')
    def test_apply_backup_drive_configuration_checks_only_selected_partition_mount(
        self,
        mock_get_mount,
        mock_get_uuid,
        mock_get_usb_id,
        mock_get_fstype,
        mock_update_fstab,
        mock_reload_mount_units,
        mock_makedirs,
        mock_run,
    ):
        runtime = SimpleNamespace(is_fake=False, default_mount_point='/media/backup')
        config_manager = MagicMock()
        config_manager.get_value.side_effect = ['/media/backup', '', '']
        smb_manager = MagicMock()
        smb_manager.get_managed_share.return_value = None

        mock_get_mount.return_value = None
        mock_get_uuid.return_value = 'UUID-1'
        mock_get_usb_id.return_value = '1234:5678'
        mock_get_fstype.return_value = 'ntfs'
        mock_update_fstab.return_value = None
        mock_run.return_value = SimpleNamespace(returncode=0, stderr='', stdout='')

        result = backup_drive_setup.apply_backup_drive_configuration(
            '/dev/sdb1',
            '/media/backup',
            True,
            config_manager,
            smb_manager,
            runtime=runtime,
        )

        self.assertEqual(result['uuid'], 'UUID-1')
        mock_get_mount.assert_called_once_with('/dev/sdb1')
        mock_reload_mount_units.assert_called_once_with(runtime=runtime)
        mock_run.assert_called_once_with(
            ['ntfs-3g', '/dev/sdb1', '/media/backup', '-o', 'rw,uid=1000,gid=1000'],
            capture_output=True,
            text=True,
        )

    @patch('backup_drive_setup.subprocess.run')
    @patch('backup_drive_setup.restore_fstab_backup')
    @patch('backup_drive_setup.os.makedirs')
    @patch('backup_drive_setup._reload_systemd_mount_units')
    @patch('backup_drive_setup.update_managed_fstab')
    @patch('backup_drive_setup._get_partition_filesystem_type')
    @patch('backup_drive_setup.get_drive_usb_id')
    @patch('backup_drive_setup.get_drive_uuid')
    @patch('backup_drive_setup._get_mount_for_partition')
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
        mock_run,
    ):
        runtime = SimpleNamespace(is_fake=False, default_mount_point='/media/backup')
        config_manager = MagicMock()
        config_manager.get_value.side_effect = ['/media/backup', 'OLD-UUID', '1234:5678']
        smb_manager = MagicMock()
        smb_manager.get_managed_share.return_value = None

        mock_get_mount.return_value = None
        mock_get_uuid.return_value = 'UUID-1'
        mock_get_usb_id.return_value = '1234:5678'
        mock_get_fstype.return_value = 'ntfs'
        mock_update_fstab.return_value = '/tmp/fstab.backup'
        mock_run.return_value = SimpleNamespace(returncode=1, stderr='busy', stdout='')

        with self.assertRaisesRegex(backup_drive_setup.BackupDriveSetupError, 'Error mounting drive: busy'):
            backup_drive_setup.apply_backup_drive_configuration(
                '/dev/sdb1',
                '/media/backup',
                True,
                config_manager,
                smb_manager,
                runtime=runtime,
            )

        mock_restore_fstab_backup.assert_called_once_with('/tmp/fstab.backup', runtime=runtime)
        self.assertEqual(mock_reload_mount_units.call_count, 2)

    @patch('backup_drive_setup.subprocess.run')
    @patch('backup_drive_setup.restore_fstab_backup')
    @patch('backup_drive_setup.os.makedirs')
    @patch('backup_drive_setup._reload_systemd_mount_units')
    @patch('backup_drive_setup.update_managed_fstab')
    @patch('backup_drive_setup._get_partition_filesystem_type')
    @patch('backup_drive_setup.get_drive_usb_id')
    @patch('backup_drive_setup.get_drive_uuid')
    @patch('backup_drive_setup._get_mount_for_partition')
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
        mock_run,
    ):
        runtime = SimpleNamespace(is_fake=False, default_mount_point='/media/backup')
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
            backup_drive_setup.BackupDriveSetupError('Failed to reload systemd after updating /etc/fstab: bad reload'),
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
            )

        mock_restore_fstab_backup.assert_called_once_with('/tmp/fstab.backup', runtime=runtime)
        self.assertEqual(mock_reload_mount_units.call_count, 2)
        mock_run.assert_not_called()

    @patch('backup_drive_setup.get_fake_state')
    @patch('backup_drive_setup.restore_fstab_backup')
    @patch('backup_drive_setup._reload_systemd_mount_units')
    @patch('backup_drive_setup.update_managed_fstab')
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
            smb_manager.update_managed_share.call_args_list[-1].kwargs,
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
