import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import backup_drive_unmount
from backup_drive_setup import BackupDriveSetupError


class FakeBackupDriveCommandAdapter:
    def __init__(self):
        self.calls = []
        self.unmount_result = SimpleNamespace(returncode=0, stderr='', stdout='')
        self.partition_device = '/dev/sdb1'

    def close_smb_share(self, mount_point):
        self.calls.append(('close_smb_share', mount_point))

    def stop_unit(self, unit_name):
        self.calls.append(('stop_unit', unit_name))

    def start_unit(self, unit_name):
        self.calls.append(('start_unit', unit_name))

    def unmount(self, mount_point):
        self.calls.append(('unmount', mount_point))
        return self.unmount_result

    def find_device_by_uuid(self, uuid):
        self.calls.append(('find_device_by_uuid', uuid))
        return self.partition_device

    def power_down_device(self, device):
        self.calls.append(('power_down_device', device))


class BackupDriveUnmountTests(unittest.TestCase):
    @patch('backup_drive_unmount._get_mount_for_partition')
    def test_is_selected_partition_managed_backup_drive_matches_live_mount_point(
        self,
        mock_get_mount,
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

    @patch('backup_drive_unmount._get_mount_for_partition', return_value=None)
    def test_is_selected_partition_managed_backup_drive_does_not_match_by_uuid_only(
        self,
        _mock_get_mount,
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

        self.assertFalse(result)
        system_utils.is_mounted.assert_not_called()

    @patch('backup_drive_unmount._get_mount_for_partition', return_value=None)
    def test_is_selected_partition_managed_backup_drive_does_not_match_unmounted_old_backup_partition(
        self,
        _mock_get_mount,
    ):
        system_utils = MagicMock()
        runtime = SimpleNamespace(is_fake=False)

        result = backup_drive_unmount.is_selected_partition_managed_backup_drive(
            '/dev/sdb1',
            '/media/backup',
            'UUID-1',
            system_utils,
            runtime=runtime,
        )

        self.assertFalse(result)
        system_utils.is_mounted.assert_not_called()

    def test_unmount_managed_backup_drive_stops_services_and_restarts_smb_without_power_down(
        self,
    ):
        runtime = SimpleNamespace(is_fake=False)
        system_utils = MagicMock()
        command_adapter = FakeBackupDriveCommandAdapter()

        backup_drive_unmount.unmount_managed_backup_drive(
            '/media/backup',
            'UUID-1',
            system_utils,
            runtime=runtime,
            power_down=False,
            command_adapter=command_adapter,
        )

        self.assertEqual(
            command_adapter.calls,
            [
                ('close_smb_share', '/media/backup'),
                ('stop_unit', 'check_mount.service'),
                ('stop_unit', 'check_health.service'),
                ('stop_unit', 'backup_cloud.service'),
                ('stop_unit', 'smbd'),
                ('stop_unit', 'nmbd'),
                ('unmount', '/media/backup'),
                ('start_unit', 'smbd'),
                ('start_unit', 'nmbd'),
            ],
        )

    def test_unmount_managed_backup_drive_can_power_down_parent_device(self):
        runtime = SimpleNamespace(is_fake=False)
        system_utils = MagicMock()
        system_utils.get_parent_device.return_value = '/dev/sdb'
        command_adapter = FakeBackupDriveCommandAdapter()

        backup_drive_unmount.unmount_managed_backup_drive(
            '/media/backup',
            'UUID-1',
            system_utils,
            runtime=runtime,
            power_down=True,
            command_adapter=command_adapter,
        )

        self.assertIn(('find_device_by_uuid', 'UUID-1'), command_adapter.calls)
        self.assertIn(('power_down_device', '/dev/sdb'), command_adapter.calls)

    def test_unmount_managed_backup_drive_restarts_smb_after_unmount_failure(self):
        runtime = SimpleNamespace(is_fake=False)
        system_utils = MagicMock()
        command_adapter = FakeBackupDriveCommandAdapter()
        command_adapter.unmount_result = SimpleNamespace(returncode=1, stderr='busy', stdout='')

        with self.assertRaisesRegex(BackupDriveSetupError, 'Failed to unmount drive: busy'):
            backup_drive_unmount.unmount_managed_backup_drive(
                '/media/backup',
                'UUID-1',
                system_utils,
                runtime=runtime,
                power_down=False,
                command_adapter=command_adapter,
            )

        self.assertEqual(
            command_adapter.calls[-2:],
            [
                ('start_unit', 'smbd'),
                ('start_unit', 'nmbd'),
            ],
        )


if __name__ == '__main__':
    unittest.main()
