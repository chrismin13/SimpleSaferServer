import unittest
import importlib
import sys
import types
from unittest.mock import MagicMock, patch

from flask import Flask


class SetupWizardTests(unittest.TestCase):
    def setUp(self):
        config_manager_module = types.ModuleType("config_manager")
        config_manager_module.ConfigManager = lambda runtime=None: types.SimpleNamespace(
            is_setup_complete=lambda: False,
        )
        system_utils_module = types.ModuleType("system_utils")
        system_utils_module.SystemUtils = lambda runtime=None: object()
        user_manager_module = types.ModuleType("user_manager")
        user_manager_module.UserManager = lambda runtime=None: types.SimpleNamespace(
            is_admin=lambda username: False,
        )
        smb_manager_module = types.ModuleType("smb_manager")
        smb_manager_module.SMBManager = lambda runtime=None: object()
        runtime_module = types.ModuleType("runtime")
        runtime_module.get_runtime = lambda: types.SimpleNamespace(is_fake=False, default_mount_point='/media/backup')
        runtime_module.get_fake_state = lambda: None

        self._module_patches = [
            patch.dict(
                sys.modules,
                {
                    "config_manager": config_manager_module,
                    "system_utils": system_utils_module,
                    "user_manager": user_manager_module,
                    "smb_manager": smb_manager_module,
                    "runtime": runtime_module,
                },
            )
        ]
        for module_patch in self._module_patches:
            module_patch.start()
        self.addCleanup(lambda: sys.modules.pop("setup_wizard", None))
        self.addCleanup(lambda: [module_patch.stop() for module_patch in reversed(self._module_patches)])

        import setup_wizard

        self.setup_wizard = importlib.reload(setup_wizard)
        self.app = Flask(__name__)
        self.app.secret_key = 'test-secret'
        self.app.register_blueprint(self.setup_wizard.setup)

    def test_list_format_drives_uses_broad_disk_scan(self):
        with patch.object(
            self.setup_wizard,
            "get_available_backup_drives",
            return_value=[{"path": "/dev/sdb", "partitions": []}],
        ) as mock_get_available_backup_drives:
            with self.app.test_client() as client:
                response = client.get("/api/setup/format-drives")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["success"], True)
        mock_get_available_backup_drives.assert_called_once_with(
            runtime=self.setup_wizard.runtime,
            ntfs_only=False,
        )

    def test_list_mount_drives_uses_ntfs_only_partition_scan(self):
        with patch.object(
            self.setup_wizard,
            "get_available_backup_drives",
            return_value=[{"path": "/dev/sdb", "partitions": []}],
        ) as mock_get_available_backup_drives:
            with self.app.test_client() as client:
                response = client.get("/api/setup/mount-drives")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["success"], True)
        mock_get_available_backup_drives.assert_called_once_with(
            runtime=self.setup_wizard.runtime,
            ntfs_only=True,
        )

    def test_setup_api_requires_login_after_setup_is_complete(self):
        completed_config = MagicMock()
        completed_config.is_setup_complete.return_value = True

        with patch.object(self.setup_wizard, 'config_manager', completed_config):
            with patch.object(self.setup_wizard, 'get_available_backup_drives') as mock_get_available_backup_drives:
                with self.app.test_client() as client:
                    response = client.get('/api/setup/format-drives')

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {'success': False, 'error': 'Please log in again.'})
        mock_get_available_backup_drives.assert_not_called()

    def test_setup_api_requires_admin_after_setup_is_complete(self):
        completed_config = MagicMock()
        completed_config.is_setup_complete.return_value = True
        non_admin_user_manager = MagicMock()
        non_admin_user_manager.is_admin.return_value = False

        with patch.object(self.setup_wizard, 'config_manager', completed_config):
            with patch.object(self.setup_wizard, 'user_manager', non_admin_user_manager):
                with patch.object(self.setup_wizard, 'get_available_backup_drives') as mock_get_available_backup_drives:
                    with self.app.test_client() as client:
                        with client.session_transaction() as session:
                            session['username'] = 'operator'
                        response = client.get('/api/setup/format-drives')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json(), {'success': False, 'error': 'Admin privileges required.'})
        non_admin_user_manager.is_admin.assert_called_once_with('operator')
        mock_get_available_backup_drives.assert_not_called()

    def test_setup_unmount_offers_managed_retry_after_busy_partition_unmount(self):
        managed_config = MagicMock()
        managed_config.is_setup_complete.return_value = False
        managed_config.get_value.side_effect = ['/media/backup', 'UUID-1']

        with patch.object(self.setup_wizard, 'config_manager', managed_config):
            with patch.object(
                self.setup_wizard,
                'unmount_selected_partition',
                side_effect=self.setup_wizard.BackupDriveSetupError('Failed to unmount partition: target is busy'),
            ) as mock_unmount_selected:
                with patch.object(
                    self.setup_wizard,
                    'is_selected_partition_managed_backup_drive',
                    return_value=True,
                ) as mock_is_managed:
                    with self.app.test_client() as client:
                        response = client.post('/api/setup/unmount', json={'partition': '/dev/sdb1'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                'success': False,
                'error': self.setup_wizard.MANAGED_UNMOUNT_RETRY_ERROR,
                'details': self.setup_wizard.MANAGED_UNMOUNT_RETRY_DETAILS,
                'can_retry_managed_unmount': True,
            },
        )
        mock_unmount_selected.assert_called_once_with('/dev/sdb1', runtime=self.setup_wizard.runtime)
        mock_is_managed.assert_called_once_with(
            '/dev/sdb1',
            '/media/backup',
            'UUID-1',
            self.setup_wizard.system_utils,
            runtime=self.setup_wizard.runtime,
        )

    def test_setup_unmount_can_retry_with_managed_backup_path(self):
        managed_config = MagicMock()
        managed_config.is_setup_complete.return_value = False
        managed_config.get_value.side_effect = ['/media/backup', 'UUID-1']

        with patch.object(self.setup_wizard, 'config_manager', managed_config):
            with patch.object(
                self.setup_wizard,
                'is_selected_partition_managed_backup_drive',
                return_value=True,
            ) as mock_is_managed:
                with patch.object(
                    self.setup_wizard,
                    'unmount_managed_backup_drive',
                ) as mock_unmount_managed:
                    with self.app.test_client() as client:
                        response = client.post(
                            '/api/setup/unmount',
                            json={'partition': '/dev/sdb1', 'force_managed': True},
                        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['success'], True)
        self.assertIn('SMB-safe retry', response.get_json()['message'])
        mock_is_managed.assert_called_once_with(
            '/dev/sdb1',
            '/media/backup',
            'UUID-1',
            self.setup_wizard.system_utils,
            runtime=self.setup_wizard.runtime,
        )
        mock_unmount_managed.assert_called_once_with(
            '/media/backup',
            'UUID-1',
            self.setup_wizard.system_utils,
            runtime=self.setup_wizard.runtime,
            power_down=False,
        )

    def test_mount_drive_returns_400_when_body_is_missing(self):
        # No Content-Type / body at all — get_json() returns None, must not raise AttributeError.
        with self.app.test_client() as client:
            response = client.post('/api/setup/mount')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {'success': False, 'error': 'partition is required'})

    def test_mount_drive_returns_400_when_partition_is_absent(self):
        # Valid JSON body but the required 'partition' key is missing.
        with self.app.test_client() as client:
            response = client.post('/api/setup/mount', json={'mount_point': '/some/path'})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {'success': False, 'error': 'partition is required'})

    # ------------------------------------------------------------------
    # get_partition_node helper — NVMe/MMC partition naming
    # ------------------------------------------------------------------

    def test_get_partition_node_standard_sata_disk(self):
        # /dev/sdb ends with a letter, so the partition is just /dev/sdb1.
        self.assertEqual(self.setup_wizard.get_partition_node('/dev/sdb'), '/dev/sdb1')

    def test_get_partition_node_raises_value_error_for_none(self):
        # The helper documents that None is invalid input.
        with self.assertRaises(ValueError):
            self.setup_wizard.get_partition_node(None)

    def test_get_partition_node_raises_value_error_for_empty_string(self):
        # The helper documents that an empty device path is invalid input.
        with self.assertRaises(ValueError):
            self.setup_wizard.get_partition_node('')

    def test_get_partition_node_raises_value_error_for_non_string(self):
        # Non-string truthy values must raise ValueError, not TypeError.
        with self.assertRaises(ValueError):
            self.setup_wizard.get_partition_node(123)

    def test_get_partition_node_nvme_disk(self):
        # NVMe paths end with a digit (/dev/nvme0n1), so a 'p' separator is
        # needed to produce /dev/nvme0n1p1.
        self.assertEqual(self.setup_wizard.get_partition_node('/dev/nvme0n1'), '/dev/nvme0n1p1')

    def test_get_partition_node_mmc_disk(self):
        # MMC/SD-card paths also end with a digit (/dev/mmcblk0).
        self.assertEqual(self.setup_wizard.get_partition_node('/dev/mmcblk0'), '/dev/mmcblk0p1')

    def test_get_partition_node_loop_device(self):
        # Loop devices end with a digit too (/dev/loop0).
        self.assertEqual(self.setup_wizard.get_partition_node('/dev/loop0'), '/dev/loop0p1')

    def test_get_partition_node_sda_disk(self):
        # Another standard disk to confirm the letter-ending branch.
        self.assertEqual(self.setup_wizard.get_partition_node('/dev/sda'), '/dev/sda1')

    # ------------------------------------------------------------------
    # format_drive — disk path validation, partprobe, and partition poll
    # ------------------------------------------------------------------

    def _post_format(self, client, disk):
        """POST /api/setup/format with a JSON body and return the response."""
        return client.post('/api/setup/format', json={'disk': disk})

    def test_format_drive_rejects_non_dev_path(self):
        # Paths that resolve outside /dev/ must be rejected without touching the disk.
        with patch('os.path.realpath', return_value='/tmp/evil'):
            with self.app.test_client() as client:
                response = self._post_format(client, '/tmp/evil')

        data = response.get_json()
        self.assertEqual(data['success'], False)
        self.assertIn('/dev/', data['error'])

    def test_format_drive_rejects_nonexistent_device(self):
        # A path under /dev/ that doesn't exist must be rejected.
        with patch('os.path.realpath', return_value='/dev/sdb'):
            with patch('os.path.exists', return_value=False):
                with self.app.test_client() as client:
                    response = self._post_format(client, '/dev/sdb')

        data = response.get_json()
        self.assertEqual(data['success'], False)
        self.assertIn('does not exist', data['error'])

    def test_format_drive_rejects_non_block_device(self):
        # A node that exists but is not a block device (e.g. /dev/null) must be rejected.
        import stat as stat_module
        non_block_stat = MagicMock()
        non_block_stat.st_mode = stat_module.S_IFCHR | 0o666  # char device, not block

        with patch('os.path.realpath', return_value='/dev/null'):
            with patch('os.path.exists', return_value=True):
                with patch('os.stat', return_value=non_block_stat):
                    with self.app.test_client() as client:
                        response = self._post_format(client, '/dev/null')

        data = response.get_json()
        self.assertEqual(data['success'], False)
        self.assertIn('block device', data['error'])

    def test_format_drive_rejects_partition_node(self):
        # Passing a partition (/dev/sda1) instead of a whole disk must be rejected.
        import stat as stat_module
        blk_stat = MagicMock()
        blk_stat.st_mode = stat_module.S_IFBLK | 0o660

        lsblk_result = MagicMock(returncode=0, stdout='part\n', stderr='')
        with patch('os.path.realpath', return_value='/dev/sda1'):
            with patch('os.path.exists', return_value=True):
                with patch('os.stat', return_value=blk_stat):
                    with patch.object(self.setup_wizard.subprocess, 'run', return_value=lsblk_result):
                        with self.app.test_client() as client:
                            response = self._post_format(client, '/dev/sda1')

        data = response.get_json()
        self.assertEqual(data['success'], False)
        self.assertIn('whole-disk', data['error'])

    def test_format_drive_handles_lsblk_not_found(self):
        # If lsblk isn't installed, return a clear error rather than crashing.
        import stat as stat_module
        blk_stat = MagicMock()
        blk_stat.st_mode = stat_module.S_IFBLK | 0o660

        with patch('os.path.realpath', return_value='/dev/sdb'):
            with patch('os.path.exists', return_value=True):
                with patch('os.stat', return_value=blk_stat):
                    with patch.object(
                        self.setup_wizard.subprocess,
                        'run',
                        side_effect=FileNotFoundError,
                    ):
                        with self.app.test_client() as client:
                            response = self._post_format(client, '/dev/sdb')

        data = response.get_json()
        self.assertEqual(data['success'], False)
        self.assertIn('verify disk type', data['error'])

    def test_format_drive_partprobe_missing_is_non_fatal(self):
        # FileNotFoundError from partprobe (not installed) must not abort formatting.
        import stat as stat_module
        blk_stat = MagicMock()
        blk_stat.st_mode = stat_module.S_IFBLK | 0o660

        # lsblk succeeds → disk is valid; fdisk succeeds → partition created;
        # partprobe raises FileNotFoundError → logged at debug, not fatal;
        # os.stat on partition shows a block device → poll succeeds immediately;
        # mkfs.ntfs succeeds → overall success.
        lsblk_ok = MagicMock(returncode=0, stdout='disk\n', stderr='')
        fdisk_ok = MagicMock(returncode=0, stdout='', stderr='')
        mkfs_ok = MagicMock(returncode=0, stdout='', stderr='')

        subprocess_call_results = iter([lsblk_ok, fdisk_ok, mkfs_ok])

        def fake_run(cmd, **kwargs):
            if cmd[0] == 'partprobe':
                raise FileNotFoundError
            return next(subprocess_call_results)

        partition_stat = MagicMock()
        partition_stat.st_mode = stat_module.S_IFBLK | 0o660

        def fake_os_stat(path):
            # Partition node exists as a block device immediately.
            return partition_stat

        with patch('os.path.realpath', return_value='/dev/sdb'):
            with patch('os.path.exists', side_effect=lambda p: p == '/dev/sdb'):
                with patch('os.stat', side_effect=fake_os_stat):
                    with patch.object(self.setup_wizard.subprocess, 'run', side_effect=fake_run):
                        with patch.object(self.setup_wizard, '_get_mounted_partitions_for_disk', return_value=[]):
                            with self.app.test_client() as client:
                                response = self._post_format(client, '/dev/sdb')

        self.assertEqual(response.get_json()['success'], True)

    def test_format_drive_partprobe_nonzero_is_non_fatal(self):
        # Non-zero exit from partprobe must be logged at debug, not abort formatting.
        import stat as stat_module
        blk_stat = MagicMock()
        blk_stat.st_mode = stat_module.S_IFBLK | 0o660

        lsblk_ok = MagicMock(returncode=0, stdout='disk\n', stderr='')
        fdisk_ok = MagicMock(returncode=0, stdout='', stderr='')
        partprobe_fail = MagicMock(returncode=1, stdout='', stderr='ioctl error')
        mkfs_ok = MagicMock(returncode=0, stdout='', stderr='')

        subprocess_calls = iter([lsblk_ok, fdisk_ok, partprobe_fail, mkfs_ok])

        partition_stat = MagicMock()
        partition_stat.st_mode = stat_module.S_IFBLK | 0o660

        def fake_os_stat(path):
            return partition_stat

        with patch('os.path.realpath', return_value='/dev/sdb'):
            with patch('os.path.exists', side_effect=lambda p: p == '/dev/sdb'):
                with patch('os.stat', side_effect=fake_os_stat):
                    with patch.object(
                        self.setup_wizard.subprocess, 'run', side_effect=lambda cmd, **kw: next(subprocess_calls)
                    ):
                        with patch.object(self.setup_wizard, '_get_mounted_partitions_for_disk', return_value=[]):
                            with self.app.test_client() as client:
                                response = self._post_format(client, '/dev/sdb')

        self.assertEqual(response.get_json()['success'], True)

    def test_format_drive_poll_timeout_returns_error(self):
        # If the partition node never appears as a block device within the
        # timeout window, format_drive must return a clear error.
        import stat as stat_module
        blk_stat = MagicMock()
        blk_stat.st_mode = stat_module.S_IFBLK | 0o660

        lsblk_ok = MagicMock(returncode=0, stdout='disk\n', stderr='')
        fdisk_ok = MagicMock(returncode=0, stdout='', stderr='')

        disk_stat = MagicMock()
        disk_stat.st_mode = stat_module.S_IFBLK | 0o660

        def fake_os_stat(path):
            if path == '/dev/sdb':
                return disk_stat
            # Partition node (/dev/sdb1) never appears — always raises OSError.
            raise OSError('no such file')

        def fake_run(cmd, **kwargs):
            if cmd[0] == 'partprobe':
                raise FileNotFoundError
            if cmd[0] == 'lsblk':
                return lsblk_ok
            if cmd[0] == 'fdisk':
                return fdisk_ok
            raise AssertionError(f'Unexpected subprocess call: {cmd}')

        # Return a low timestamp on the first call (deadline = 0 + timeout),
        # then a timestamp past the deadline on the second call so the poll
        # loop exits immediately.
        timeout = self.setup_wizard.PARTITION_POLL_TIMEOUT_SECONDS
        monotonic_seq = iter([0.0, timeout + 1.0])

        with patch('os.path.realpath', return_value='/dev/sdb'):
            with patch('os.path.exists', side_effect=lambda p: p == '/dev/sdb'):
                with patch('os.stat', side_effect=fake_os_stat):
                    with patch.object(self.setup_wizard.subprocess, 'run', side_effect=fake_run):
                        with patch.object(self.setup_wizard, '_get_mounted_partitions_for_disk', return_value=[]):
                            with patch.object(self.setup_wizard.time, 'monotonic', side_effect=monotonic_seq):
                                with self.app.test_client() as client:
                                    response = self._post_format(client, '/dev/sdb')

        data = response.get_json()
        self.assertEqual(data['success'], False)
        self.assertIn('did not appear', data['error'])

