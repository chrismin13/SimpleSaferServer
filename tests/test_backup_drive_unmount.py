import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import backup_drive_unmount
from backup_drive_setup import BackupDriveSetupError


class BackupDriveUnmountTests(unittest.TestCase):
    @patch('backup_drive_unmount.get_drive_uuid')
    @patch('backup_drive_unmount._get_mount_for_partition')
    def test_is_selected_partition_managed_backup_drive_matches_live_mount_point(
        self,
        mock_get_mount,
        mock_get_uuid,
    ):
        system_utils = MagicMock()
        runtime = SimpleNamespace(is_fake=False)
        mock_get_mount.return_value = {'device': '/dev/sdb1', 'mount_point': '/media/backup'}

        result = backup_drive_unmount.is_selected_partition_managed_backup_drive(
            '/dev/sdb1',
            '/media/backup',
            'UUID-1',
            system_utils,
            runtime=runtime,
        )

        self.assertTrue(result)
        system_utils.is_mounted.assert_not_called()
        mock_get_uuid.assert_not_called()

    @patch('backup_drive_unmount.get_drive_uuid', return_value='UUID-1')
    @patch('backup_drive_unmount._get_mount_for_partition', return_value=None)
    def test_is_selected_partition_managed_backup_drive_matches_uuid_only_when_managed_mount_is_live(
        self,
        _mock_get_mount,
        mock_get_uuid,
    ):
        system_utils = MagicMock()
        system_utils.is_mounted.return_value = True
        runtime = SimpleNamespace(is_fake=False)

        result = backup_drive_unmount.is_selected_partition_managed_backup_drive(
            '/dev/sdb1',
            '/media/backup',
            'UUID-1',
            system_utils,
            runtime=runtime,
        )

        self.assertTrue(result)
        system_utils.is_mounted.assert_called_once_with('/media/backup')
        mock_get_uuid.assert_called_once_with('/dev/sdb1')

    @patch('backup_drive_unmount.get_drive_uuid', return_value='UUID-1')
    @patch('backup_drive_unmount._get_mount_for_partition', return_value=None)
    def test_is_selected_partition_managed_backup_drive_does_not_match_unmounted_old_backup_partition(
        self,
        _mock_get_mount,
        mock_get_uuid,
    ):
        system_utils = MagicMock()
        system_utils.is_mounted.return_value = False
        runtime = SimpleNamespace(is_fake=False)

        result = backup_drive_unmount.is_selected_partition_managed_backup_drive(
            '/dev/sdb1',
            '/media/backup',
            'UUID-1',
            system_utils,
            runtime=runtime,
        )

        self.assertFalse(result)
        system_utils.is_mounted.assert_called_once_with('/media/backup')
        mock_get_uuid.assert_not_called()

    @patch('backup_drive_unmount.subprocess.run')
    def test_unmount_managed_backup_drive_stops_services_and_restarts_smb_without_power_down(self, mock_run):
        runtime = SimpleNamespace(is_fake=False)
        system_utils = MagicMock()
        mock_run.return_value = SimpleNamespace(returncode=0, stderr='', stdout='')

        backup_drive_unmount.unmount_managed_backup_drive(
            '/media/backup',
            'UUID-1',
            system_utils,
            runtime=runtime,
            power_down=False,
        )

        self.assertEqual(
            mock_run.call_args_list,
            [
                call(['sudo', 'smbcontrol', 'all', 'close-share', '/media/backup'], check=False),
                call(['sudo', 'systemctl', 'stop', 'check_mount.service'], check=False),
                call(['sudo', 'systemctl', 'stop', 'check_health.service'], check=False),
                call(['sudo', 'systemctl', 'stop', 'backup_cloud.service'], check=False),
                call(['sudo', 'systemctl', 'stop', 'smbd'], check=False),
                call(['sudo', 'systemctl', 'stop', 'nmbd'], check=False),
                call(['sudo', 'umount', '/media/backup'], capture_output=True, text=True),
                call(['sudo', 'systemctl', 'start', 'smbd'], check=False),
                call(['sudo', 'systemctl', 'start', 'nmbd'], check=False),
            ],
        )

    @patch('backup_drive_unmount.subprocess.run')
    def test_unmount_managed_backup_drive_can_power_down_parent_device(self, mock_run):
        runtime = SimpleNamespace(is_fake=False)
        system_utils = MagicMock()
        system_utils.get_parent_device.return_value = '/dev/sdb'
        mock_run.side_effect = [
            SimpleNamespace(returncode=0, stderr='', stdout=''),
            SimpleNamespace(returncode=0, stderr='', stdout=''),
            SimpleNamespace(returncode=0, stderr='', stdout=''),
            SimpleNamespace(returncode=0, stderr='', stdout=''),
            SimpleNamespace(returncode=0, stderr='', stdout=''),
            SimpleNamespace(returncode=0, stderr='', stdout=''),
            SimpleNamespace(returncode=0, stderr='', stdout=''),
            SimpleNamespace(returncode=0, stderr='', stdout='/dev/sdb1\n'),
            SimpleNamespace(returncode=0, stderr='', stdout=''),
            SimpleNamespace(returncode=0, stderr='', stdout=''),
            SimpleNamespace(returncode=0, stderr='', stdout=''),
        ]

        backup_drive_unmount.unmount_managed_backup_drive(
            '/media/backup',
            'UUID-1',
            system_utils,
            runtime=runtime,
            power_down=True,
        )

        self.assertIn(
            call(['blkid', '-t', 'UUID=UUID-1', '-o', 'device'], capture_output=True, text=True),
            mock_run.call_args_list,
        )
        self.assertIn(call(['sudo', 'hdparm', '-y', '/dev/sdb'], check=False), mock_run.call_args_list)

    @patch('backup_drive_unmount.subprocess.run')
    def test_unmount_managed_backup_drive_restarts_smb_after_unmount_failure(self, mock_run):
        runtime = SimpleNamespace(is_fake=False)
        system_utils = MagicMock()
        mock_run.side_effect = [
            SimpleNamespace(returncode=0, stderr='', stdout=''),
            SimpleNamespace(returncode=0, stderr='', stdout=''),
            SimpleNamespace(returncode=0, stderr='', stdout=''),
            SimpleNamespace(returncode=0, stderr='', stdout=''),
            SimpleNamespace(returncode=0, stderr='', stdout=''),
            SimpleNamespace(returncode=0, stderr='', stdout=''),
            SimpleNamespace(returncode=1, stderr='busy', stdout=''),
            SimpleNamespace(returncode=0, stderr='', stdout=''),
            SimpleNamespace(returncode=0, stderr='', stdout=''),
        ]

        with self.assertRaisesRegex(BackupDriveSetupError, 'Failed to unmount drive: busy'):
            backup_drive_unmount.unmount_managed_backup_drive(
                '/media/backup',
                'UUID-1',
                system_utils,
                runtime=runtime,
                power_down=False,
            )

        self.assertEqual(
            mock_run.call_args_list[-2:],
            [
                call(['sudo', 'systemctl', 'start', 'smbd'], check=False),
                call(['sudo', 'systemctl', 'start', 'nmbd'], check=False),
            ],
        )


if __name__ == '__main__':
    unittest.main()
