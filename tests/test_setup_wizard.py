import unittest
import importlib
import sys
import types
from unittest.mock import patch

from flask import Flask


class SetupWizardTests(unittest.TestCase):
    def setUp(self):
        config_manager_module = types.ModuleType("config_manager")
        config_manager_module.ConfigManager = lambda runtime=None: object()
        system_utils_module = types.ModuleType("system_utils")
        system_utils_module.SystemUtils = lambda runtime=None: object()
        user_manager_module = types.ModuleType("user_manager")
        user_manager_module.UserManager = lambda runtime=None: object()
        smb_manager_module = types.ModuleType("smb_manager")
        smb_manager_module.SMBManager = lambda runtime=None: object()
        runtime_module = types.ModuleType("runtime")
        runtime_module.get_runtime = lambda: types.SimpleNamespace(is_fake=False)
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
        self.app.register_blueprint(self.setup_wizard.setup)

    def test_list_drives_uses_ntfs_only_partition_scan(self):
        with patch.object(
            self.setup_wizard,
            "get_available_backup_drives",
            return_value=[{"path": "/dev/sdb", "partitions": []}],
        ) as mock_get_available_backup_drives:
            with self.app.test_client() as client:
                response = client.get("/api/setup/drives")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["success"], True)
        mock_get_available_backup_drives.assert_called_once_with(
            runtime=self.setup_wizard.runtime,
            ntfs_only=True,
        )
