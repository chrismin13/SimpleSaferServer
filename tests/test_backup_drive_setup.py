import unittest
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
        mock_blkid.assert_called_once_with('/dev/sdb1')

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
        mock_makedirs,
        mock_run,
    ):
        runtime = SimpleNamespace(is_fake=False, default_mount_point='/media/backup')
        config_manager = MagicMock()
        config_manager.get_value.side_effect = ['/media/backup', '', '']
        smb_manager = MagicMock()
        smb_manager.get_shares.return_value = []

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
        mock_run.assert_called_once_with(
            ['ntfs-3g', '/dev/sdb1', '/media/backup', '-o', 'rw,uid=1000,gid=1000'],
            capture_output=True,
            text=True,
        )


if __name__ == '__main__':
    unittest.main()
