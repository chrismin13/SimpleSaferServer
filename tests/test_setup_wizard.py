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
