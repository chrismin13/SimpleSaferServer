import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask import Flask

from simple_safer_server.core.module_lifecycle import ownership_manifest_for_runtime
from simple_safer_server.modules.cloud_backup import MegaFolderList
from simple_safer_server.services.server_identity import ServerIdentityError


def _tool_path(name):
    if name == "update-ca-certificates":
        return "/usr/sbin/update-ca-certificates"
    return None


class FakeCloudBackupService:
    def __init__(self):
        self.calls = []

    def list_mega_folders(self, data):
        self.calls.append(("list_mega_folders", data))
        path = data.get("path", "/")
        parent = "/".join(path.rstrip("/").split("/")[:-1]) or "/"
        return MegaFolderList(folders=["Backups"], path=path, parent=parent)

    def create_mega_folder(self, data):
        self.calls.append(("create_mega_folder", data))

    def save_config(self, data):
        self.calls.append(("save_config", data))
        return {}


class FakeServerIdentityService:
    def __init__(self):
        self.calls = []

    def save_server_name(self, server_name):
        self.calls.append(server_name)
        if server_name == "bad name":
            raise ServerIdentityError(
                "Server name may only contain letters, numbers, and hyphens, and cannot start or end with a hyphen."
            )
        return types.SimpleNamespace(server_name=server_name, hostname=server_name, warning="")


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
        user_manager_module.admin_required = lambda route_handler: route_handler
        user_manager_module.api_admin_required = lambda route_handler: route_handler
        smb_manager_module = types.ModuleType("smb_manager")
        smb_manager_module.SMBManager = lambda runtime=None: object()
        runtime_module = types.ModuleType("runtime")
        runtime_module.get_runtime = lambda: types.SimpleNamespace(
            is_fake=False, default_mount_point='/media/backup'
        )
        runtime_module.get_fake_state = lambda: None

        self._module_patches = [
            patch.dict(
                sys.modules,
                {
                    "simple_safer_server.services.config_manager": config_manager_module,
                    "simple_safer_server.services.system_utils": system_utils_module,
                    "simple_safer_server.services.user_manager": user_manager_module,
                    "simple_safer_server.modules.file_sharing": smb_manager_module,
                    "simple_safer_server.services.runtime": runtime_module,
                },
            )
        ]
        for module_patch in self._module_patches:
            module_patch.start()
        self.addCleanup(
            lambda: [module_patch.stop() for module_patch in reversed(self._module_patches)]
        )

        sys.modules.pop("simple_safer_server.routes.setup_wizard", None)
        routes_package = importlib.import_module("simple_safer_server.routes")
        if hasattr(routes_package, "setup_wizard"):
            delattr(routes_package, "setup_wizard")
        self.addCleanup(lambda: sys.modules.pop("simple_safer_server.routes.setup_wizard", None))

        self.setup_wizard = importlib.import_module("simple_safer_server.routes.setup_wizard")
        self.app = Flask(__name__)
        self.app.secret_key = 'test-secret'
        self.cloud_backup_service = FakeCloudBackupService()
        self.server_identity_service = FakeServerIdentityService()
        self.runtime_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.runtime_dir.cleanup)
        self.runtime = types.SimpleNamespace(data_dir=Path(self.runtime_dir.name), is_fake=False)
        self.app.extensions["simple_safer_server"] = types.SimpleNamespace(
            cloud_backup_service=self.cloud_backup_service,
            server_identity_service=self.server_identity_service,
            runtime=self.runtime,
        )
        self.app.register_error_handler(
            self.setup_wizard.ApiProblem,
            lambda error: self.setup_wizard.json_problem(error),
        )
        self.app.register_blueprint(self.setup_wizard.setup)

    def assertDataResponse(self, response, expected_data=None):
        payload = response.get_json()
        self.assertIn("data", payload)
        self.assertEqual(payload["data"], expected_data or {})
        return payload

    def assertProblemDetail(self, response, detail):
        payload = response.get_json()
        self.assertEqual(payload["detail"], detail)
        self.assertIn("type", payload)
        return payload

    def test_setup_wizard_does_not_create_services_at_import_time(self):
        self.assertIsNone(self.setup_wizard.config_manager)
        self.assertIsNone(self.setup_wizard.user_manager)
        self.assertIsNone(self.setup_wizard.server_identity_service)

    def test_first_run_setup_api_does_not_construct_user_manager_for_access_check(self):
        config_manager = MagicMock()
        config_manager.is_setup_complete.return_value = False
        user_manager_factory = MagicMock(side_effect=AssertionError("user manager not needed"))

        with (
            patch.object(self.setup_wizard, "config_manager", config_manager),
            patch.object(self.setup_wizard, "UserManager", user_manager_factory),
            self.app.test_client() as client,
        ):
            response = client.post("/api/setup/user", json={"username": "admin"})

        self.assertEqual(response.status_code, 400)
        user_manager_factory.assert_not_called()

    def test_list_format_drives_uses_broad_disk_scan(self):
        with (
            patch.object(
                self.setup_wizard,
                "get_available_backup_drives",
                return_value=[{"path": "/dev/sdb", "partitions": []}],
            ) as mock_get_available_backup_drives,
            self.app.test_client() as client,
        ):
            response = client.get("/api/setup/format-drives")

        self.assertEqual(response.status_code, 200)
        self.assertDataResponse(response, {"drives": [{"path": "/dev/sdb", "partitions": []}]})
        mock_get_available_backup_drives.assert_called_once_with(
            runtime=self.runtime,
            ntfs_only=False,
        )

    def test_list_mount_drives_uses_ntfs_only_partition_scan(self):
        with (
            patch.object(
                self.setup_wizard,
                "get_available_backup_drives",
                return_value=[{"path": "/dev/sdb", "partitions": []}],
            ) as mock_get_available_backup_drives,
            self.app.test_client() as client,
        ):
            response = client.get("/api/setup/mount-drives")

        self.assertEqual(response.status_code, 200)
        self.assertDataResponse(response, {"drives": [{"path": "/dev/sdb", "partitions": []}]})
        mock_get_available_backup_drives.assert_called_once_with(
            runtime=self.runtime,
            ntfs_only=True,
        )

    def test_setup_api_requires_login_after_setup_is_complete(self):
        completed_config = MagicMock()
        completed_config.is_setup_complete.return_value = True

        with patch.object(self.setup_wizard, 'config_manager', completed_config):
            with patch.object(
                self.setup_wizard, 'get_available_backup_drives'
            ) as mock_get_available_backup_drives:
                with self.app.test_client() as client:
                    response = client.get('/api/setup/format-drives')

        self.assertEqual(response.status_code, 401)
        self.assertProblemDetail(response, 'Please log in again.')
        mock_get_available_backup_drives.assert_not_called()

    def test_setup_list_path_returns_folders_and_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            temp_path = Path(tempdir)
            (temp_path / "media").mkdir()
            (temp_path / "readme.txt").write_text("hello", encoding="utf-8")

            with self.app.test_client() as client:
                response = client.post("/api/setup/list-path", json={"path": tempdir})

        self.assertEqual(response.status_code, 200)
        self.assertDataResponse(
            response,
            {
                "path": tempdir,
                "parent": str(Path(tempdir).parent),
                "dirs": ["media"],
                "files": ["readme.txt"],
                "entries": [
                    {"name": "media", "type": "folder"},
                    {"name": "readme.txt", "type": "file"},
                ],
            },
        )

    def test_setup_mega_connect_delegates_to_cloud_backup_service(self):
        with self.app.test_client() as client:
            response = client.post(
                "/api/setup/mega/connect",
                json={"email": "user@example.com", "password": "secret"},
            )

        self.assertDataResponse(response, {"folders": ["Backups"]})
        self.assertEqual(
            self.cloud_backup_service.calls,
            [
                (
                    "list_mega_folders",
                    {"email": "user@example.com", "password": "secret", "path": "/"},
                )
            ],
        )

    def test_setup_mega_list_folders_delegates_to_cloud_backup_service(self):
        with self.app.test_client() as client:
            response = client.post(
                "/api/setup/mega/list_folders",
                json={"email": "user@example.com", "password": "secret", "path": "/Photos"},
            )

        self.assertDataResponse(
            response,
            {"folders": ["Backups"], "path": "/Photos", "parent": "/"},
        )
        self.assertEqual(
            self.cloud_backup_service.calls,
            [
                (
                    "list_mega_folders",
                    {"email": "user@example.com", "password": "secret", "path": "/Photos"},
                )
            ],
        )

    def test_setup_mega_create_folder_delegates_to_cloud_backup_service(self):
        with self.app.test_client() as client:
            response = client.post(
                "/api/setup/mega/create_folder",
                json={
                    "email": "user@example.com",
                    "password": "secret",
                    "path": "/",
                    "folder_name": "Backups",
                },
            )

        self.assertDataResponse(response)
        self.assertEqual(
            self.cloud_backup_service.calls,
            [
                (
                    "create_mega_folder",
                    {
                        "email": "user@example.com",
                        "password": "secret",
                        "path": "/",
                        "folder_name": "Backups",
                    },
                )
            ],
        )

    def test_setup_mega_save_delegates_to_cloud_backup_service(self):
        with (
            patch("simple_safer_server.core.module_checks.shutil.which", return_value="/usr/bin/rclone"),
            self.app.test_client() as client,
        ):
            response = client.post(
                "/api/setup/mega/save",
                json={"email": "user@example.com", "password": "secret", "folder": "/Backups"},
            )

        self.assertDataResponse(response)
        self.assertEqual(
            self.cloud_backup_service.calls,
            [
                (
                    "save_config",
                    {
                        "cloud_mode": "mega",
                        "mega_email": "user@example.com",
                        "mega_password": "secret",
                        "mega_folder": "/Backups",
                    },
                )
            ],
        )
        records = ownership_manifest_for_runtime(self.runtime).list_records()
        self.assertEqual(
            [record.identifier for record in records],
            ['/etc/SimpleSaferServer/rclone/rclone.conf'],
        )

    def test_setup_rclone_delegates_to_cloud_backup_service(self):
        with (
            patch("simple_safer_server.core.module_checks.shutil.which", return_value="/usr/bin/rclone"),
            self.app.test_client() as client,
        ):
            response = client.post(
                "/api/setup/rclone",
                json={"config": "[remote]\ntype = test\n", "remote_name": "remote:/Backups"},
            )

        self.assertDataResponse(response)
        self.assertEqual(
            self.cloud_backup_service.calls,
            [
                (
                    "save_config",
                    {
                        "cloud_mode": "advanced",
                        "rclone_config": "[remote]\ntype = test\n",
                        "remote_name": "remote:/Backups",
                    },
                )
            ],
        )
        records = ownership_manifest_for_runtime(self.runtime).list_records()
        self.assertEqual(
            [record.identifier for record in records],
            ['/etc/SimpleSaferServer/rclone/rclone.conf'],
        )

    def test_setup_api_requires_admin_after_setup_is_complete(self):
        completed_config = MagicMock()
        completed_config.is_setup_complete.return_value = True
        non_admin_user_manager = MagicMock()
        non_admin_user_manager.is_admin.return_value = False

        with patch.object(self.setup_wizard, 'config_manager', completed_config):
            with patch.object(self.setup_wizard, 'user_manager', non_admin_user_manager):
                with patch.object(
                    self.setup_wizard, 'get_available_backup_drives'
                ) as mock_get_available_backup_drives:
                    with self.app.test_client() as client:
                        with client.session_transaction() as session:
                            session['username'] = 'operator'
                        response = client.get('/api/setup/format-drives')

        self.assertEqual(response.status_code, 403)
        self.assertProblemDetail(response, 'Admin privileges required.')
        non_admin_user_manager.is_admin.assert_called_once_with('operator')
        mock_get_available_backup_drives.assert_not_called()

    def test_setup_unmount_offers_managed_retry_after_busy_partition_unmount(self):
        helper = MagicMock()
        helper.run.return_value = types.SimpleNamespace(data={'can_retry_managed_unmount': True})
        self.app.extensions["simple_safer_server"].privileged_actions = helper

        with self.app.test_client() as client:
            response = client.post('/api/setup/unmount', json={'partition': '/dev/sdb1'})

        self.assertEqual(response.status_code, 400)
        data = self.assertProblemDetail(response, self.setup_wizard.MANAGED_UNMOUNT_RETRY_ERROR)
        self.assertEqual(data['details'], self.setup_wizard.MANAGED_UNMOUNT_RETRY_DETAILS)
        self.assertEqual(data['can_retry_managed_unmount'], True)
        helper.run.assert_called_once_with(
            'storage.unmount',
            {'disk': '', 'partition': '/dev/sdb1', 'force_managed': False},
        )

    def test_setup_unmount_can_retry_with_managed_backup_path(self):
        helper = MagicMock()
        helper.run.return_value = types.SimpleNamespace(
            data={
                'message': (
                    'Drive unmounted after the SMB-safe retry temporarily stopped SMB access '
                    'and related background backup tasks.'
                )
            }
        )
        self.app.extensions["simple_safer_server"].privileged_actions = helper

        with self.app.test_client() as client:
            response = client.post(
                '/api/setup/unmount',
                json={'partition': '/dev/sdb1', 'force_managed': True},
            )

        self.assertEqual(response.status_code, 200)
        self.assertDataResponse(response)
        self.assertIn('SMB-safe retry', response.get_json()['message'])
        helper.run.assert_called_once_with(
            'storage.unmount',
            {'disk': '', 'partition': '/dev/sdb1', 'force_managed': True},
        )

    def test_mount_drive_returns_400_when_body_is_missing(self):
        # No Content-Type / body at all — get_json() returns None, must not raise AttributeError.
        with self.app.test_client() as client:
            response = client.post('/api/setup/mount')

        self.assertEqual(response.status_code, 400)
        self.assertProblemDetail(response, 'Request body must be a JSON object.')

    def test_mount_drive_returns_400_when_body_is_invalid_json(self):
        with self.app.test_client() as client:
            response = client.post(
                '/api/setup/mount',
                data='{',
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertProblemDetail(response, 'Request body must be a JSON object.')

    def test_mount_drive_returns_400_when_body_is_not_object(self):
        with self.app.test_client() as client:
            response = client.post('/api/setup/mount', json=[1, 2, 3])

        self.assertEqual(response.status_code, 400)
        self.assertProblemDetail(response, 'Request body must be a JSON object.')

    def test_mount_drive_returns_400_when_partition_is_absent(self):
        # Valid JSON body but the required 'partition' key is missing.
        with self.app.test_client() as client:
            response = client.post('/api/setup/mount', json={'mount_point': '/some/path'})

        self.assertEqual(response.status_code, 400)
        self.assertProblemDetail(response, 'partition is required')

    def test_mount_drive_uses_privileged_managed_drive_action(self):
        helper = MagicMock()
        helper.run.return_value = types.SimpleNamespace(
            data={
                'message': 'Successfully configured /dev/sdb1 at /media/backup',
                'mount_point': '/media/backup',
            }
        )
        self.app.extensions["simple_safer_server"].privileged_actions = helper

        with self.app.test_client() as client:
            response = client.post(
                '/api/setup/mount',
                json={
                    'partition': '/dev/sdb1',
                    'mount_point': '/media/backup',
                    'ntfs_driver': 'ntfs3',
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()['message'],
            'Successfully configured /dev/sdb1 at /media/backup',
        )
        helper.run.assert_called_once_with(
            'storage.managed-drive',
            {
                'partition': '/dev/sdb1',
                'mount_point': '/media/backup',
                'ntfs_driver': 'ntfs3',
            },
        )

    # ------------------------------------------------------------------
    # format_drive — disk path validation, partprobe, and partition poll
    # ------------------------------------------------------------------

    def _post_format(self, client, disk):
        """POST /api/setup/format with a JSON body and return the response."""
        return client.post('/api/setup/format', json={'disk': disk})

    def test_format_drive_rejects_missing_body(self):
        # A POST with no JSON body at all must return a clear error, not AttributeError.
        with self.app.test_client() as client:
            response = client.post('/api/setup/format')

        self.assertEqual(response.status_code, 400)
        self.assertProblemDetail(response, 'Request body must be a JSON object.')

    def test_format_drive_rejects_non_dict_body(self):
        # A JSON body that is not an object (e.g. an array) must be rejected
        # clearly rather than raising an AttributeError on .get('disk').
        with self.app.test_client() as client:
            response = client.post('/api/setup/format', json=[1, 2, 3])

        data = response.get_json()
        self.assertEqual(response.status_code, 400)
        self.assertIn('JSON object', data['detail'])

    def test_create_user_returns_400_when_required_fields_are_missing(self):
        with self.app.test_client() as client:
            response = client.post('/api/setup/user', json={'username': 'admin'})

        self.assertEqual(response.status_code, 400)
        self.assertProblemDetail(response, 'Username and password are required')

    def test_create_user_persists_canonical_setup_username(self):
        config_manager = MagicMock()
        config_manager.is_setup_complete.return_value = False
        user_manager = MagicMock()
        user_manager.create_user.return_value = (True, 'created')

        with patch.object(self.setup_wizard, 'config_manager', config_manager):
            with patch.object(self.setup_wizard, 'user_manager', user_manager):
                with self.app.test_client() as client:
                    response = client.post(
                        '/api/setup/user',
                        json={'username': 'admin', 'password': 'secret-pass'},
                    )

        self.assertEqual(response.status_code, 200)
        config_manager.set_value.assert_called_once_with('system', 'username', 'admin')

    def test_setup_system_info_updates_server_identity(self):
        config_manager = MagicMock()
        config_manager.is_setup_complete.return_value = False

        with patch.object(self.setup_wizard, 'config_manager', config_manager):
            with self.app.test_client() as client:
                response = client.post(
                    '/api/setup/system',
                    json={'server_name': 'simple-safer'},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.server_identity_service.calls, ['simple-safer'])

    def test_setup_system_info_rejects_invalid_server_name(self):
        config_manager = MagicMock()
        config_manager.is_setup_complete.return_value = False

        with patch.object(self.setup_wizard, 'config_manager', config_manager):
            with self.app.test_client() as client:
                response = client.post(
                    '/api/setup/system',
                    json={'server_name': 'bad name'},
                )

        self.assertEqual(response.status_code, 400)
        self.assertProblemDetail(
            response,
            'Server name may only contain letters, numbers, and hyphens, and cannot start or end with a hyphen.',
        )

    def test_setup_email_rejects_out_of_range_smtp_port(self):
        helper = MagicMock()
        self.app.extensions["simple_safer_server"].privileged_actions = helper

        with self.app.test_client() as client:
            response = client.post(
                '/api/setup/email',
                json={
                    'emailAddress': 'admin@example.com',
                    'fromAddress': 'server@example.com',
                    'smtpServer': 'smtp.example.com',
                    'smtpPort': '65536',
                    'smtpUsername': 'server',
                    'smtpPassword': 'secret',
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertProblemDetail(response, 'SMTP port must be between 1 and 65535')
        helper.run.assert_not_called()

    def test_setup_email_writes_trimmed_smtp_port(self):
        helper = MagicMock()
        self.app.extensions["simple_safer_server"].privileged_actions = helper
        config_manager = MagicMock()
        config_manager.is_setup_complete.return_value = False

        with (
            patch.object(self.setup_wizard, 'config_manager', config_manager),
            patch("simple_safer_server.core.module_checks.shutil.which", _tool_path),
        ):
            with self.app.test_client() as client:
                response = client.post(
                    '/api/setup/email',
                    json={
                        'emailAddress': 'admin@example.com',
                        'fromAddress': 'server@example.com',
                        'smtpServer': 'smtp.example.com',
                        'smtpPort': ' 587 ',
                        'smtpUsername': 'server',
                        'smtpPassword': 'secret',
                    },
                )

        self.assertEqual(response.status_code, 200)
        helper.run.assert_called_once_with(
            'alerts.write-smtp-config',
            {
                'from_address': 'server@example.com',
                'smtp_server': 'smtp.example.com',
                'smtp_port': '587',
                'smtp_username': 'server',
                'smtp_password': 'secret',
            },
        )
        records = ownership_manifest_for_runtime(self.runtime).list_records()
        self.assertEqual(
            [record.identifier for record in records],
            ['<config>/smtp.conf', '<config>/alerts.json'],
        )

    def test_setup_email_runs_module_preflight_before_helper(self):
        helper = MagicMock()
        self.app.extensions["simple_safer_server"].privileged_actions = helper

        with (
            patch.object(self.setup_wizard, "config_manager") as config_manager,
            patch.object(
                self.setup_wizard,
                "ensure_module_can_apply",
                side_effect=self.setup_wizard.ModuleLifecycleError("Alerts cannot be applied."),
            ),
            self.app.test_client() as client,
        ):
            config_manager.is_setup_complete.return_value = False
            response = client.post(
                "/api/setup/email",
                json={
                    "emailAddress": "admin@example.com",
                    "fromAddress": "server@example.com",
                    "smtpServer": "smtp.example.com",
                    "smtpPort": "587",
                    "smtpUsername": "server",
                    "smtpPassword": "secret",
                },
            )

        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.get_json()["type"].endswith("#module-setup-required"))
        helper.run.assert_not_called()

    def test_setup_schedule_rejects_single_digit_hour(self):
        config_manager = MagicMock()
        config_manager.is_setup_complete.return_value = False

        with patch.object(self.setup_wizard, 'config_manager', config_manager):
            with self.app.test_client() as client:
                response = client.post(
                    '/api/setup/schedule',
                    json={'time': '7:05', 'bandwidth_limit': ''},
                )

        self.assertEqual(response.status_code, 400)
        self.assertProblemDetail(response, 'Invalid time format')
        config_manager.set_value.assert_not_called()

    def test_setup_schedule_saves_two_digit_time(self):
        config_manager = MagicMock()
        config_manager.is_setup_complete.return_value = False

        with patch.object(self.setup_wizard, 'config_manager', config_manager):
            with self.app.test_client() as client:
                response = client.post(
                    '/api/setup/schedule',
                    json={'time': '07:05', 'bandwidth_limit': '4M'},
                )

        self.assertEqual(response.status_code, 200)
        config_manager.set_value.assert_any_call('schedule', 'backup_cloud_time', '07:05')
        config_manager.set_value.assert_any_call('schedule', 'configured', 'true')
        config_manager.set_value.assert_any_call('backup', 'bandwidth_limit', '4M')

    def test_setup_schedule_requires_time(self):
        config_manager = MagicMock()
        config_manager.is_setup_complete.return_value = False

        with patch.object(self.setup_wizard, 'config_manager', config_manager):
            with self.app.test_client() as client:
                response = client.post('/api/setup/schedule', json={'bandwidth_limit': '4M'})

        self.assertEqual(response.status_code, 400)
        self.assertProblemDetail(response, 'Missing required fields')
        config_manager.set_value.assert_not_called()

    def test_skip_cloud_backup_saves_explicit_disabled_state(self):
        config_manager = MagicMock()
        config_manager.is_setup_complete.return_value = False

        with patch.object(self.setup_wizard, 'config_manager', config_manager):
            with self.app.test_client() as client:
                response = client.post('/api/setup/cloud-backup/skip')

        self.assertEqual(response.status_code, 200)
        config_manager.set_value.assert_any_call('backup', 'cloud_enabled', 'false')
        config_manager.set_value.assert_any_call('backup', 'cloud_skipped', 'true')
        config_manager.set_value.assert_any_call('backup', 'cloud_mode', '')
        config_manager.set_value.assert_any_call('backup', 'rclone_dir', '')

    def test_complete_setup_allows_skipped_cloud_backup_without_rclone_dir(self):
        config_manager = MagicMock()
        config_manager.is_setup_complete.return_value = False
        config_manager.get_all_config.return_value = {
            'system': {'username': 'admin', 'server_name': 'test-server'},
            'backup': {
                'mount_point': '/srv/storage',
                'email_address': 'admin@example.com',
                'cloud_enabled': 'false',
            },
            'storage': {
                'mode': 'existing_folder',
                'path': '/srv/storage',
                'storage_id': 'storage-id',
            },
            'schedule': {'backup_cloud_time': '03:00', 'configured': 'true'},
        }

        with patch.object(self.setup_wizard, 'config_manager', config_manager):
            with self.app.test_client() as client:
                response = client.post('/api/setup/complete')

        self.assertEqual(response.status_code, 200)
        config_manager.mark_setup_complete.assert_called_once()

    def test_complete_setup_requires_explicit_schedule_choice(self):
        config_manager = MagicMock()
        config_manager.is_setup_complete.return_value = False
        config_manager.get_all_config.return_value = {
            'system': {'username': 'admin', 'server_name': 'sss'},
            'backup': {
                'mount_point': '/media/backup',
                'email_address': 'admin@example.com',
                'cloud_enabled': 'false',
            },
            'storage': {
                'mode': 'existing_folder',
                'path': '/media/backup',
                'storage_id': 'storage-id',
            },
            'schedule': {'backup_cloud_time': '03:00', 'configured': 'false'},
        }

        with patch.object(self.setup_wizard, 'config_manager', config_manager):
            with self.app.test_client() as client:
                response = client.post('/api/setup/complete')

        self.assertEqual(response.status_code, 400)
        self.assertProblemDetail(response, 'Missing required fields')
        self.assertEqual(response.get_json()['details'], ['Missing schedule.configured'])

    def test_setup_readiness_returns_shared_checklist(self):
        smtp_dir = Path(tempfile.mkdtemp())
        smtp_path = smtp_dir / "smtp.conf"
        self.addCleanup(lambda: smtp_dir.rmdir())
        self.addCleanup(lambda: smtp_path.unlink(missing_ok=True))
        smtp_path.write_text(
            "\n".join(
                [
                    "host smtp.example.com",
                    "port 587",
                    "from sss@example.com",
                    "user admin@example.com",
                    "password secret",
                ]
            ),
            encoding="utf-8",
        )
        config_manager = MagicMock()
        config_manager.is_setup_complete.return_value = False
        config_manager.get_all_config.return_value = {
            'system': {'username': 'admin', 'server_name': 'sss'},
            'backup': {
                'mount_point': '/media/backup',
                'email_address': 'admin@example.com',
                'from_address': 'sss@example.com',
                'cloud_enabled': 'true',
                'cloud_skipped': 'false',
                'rclone_dir': 'mega:/Backups',
            },
            'storage': {
                'mode': 'existing_folder',
                'path': '/media/backup',
                'storage_id': 'storage-id',
            },
            'schedule': {'backup_cloud_time': '03:00', 'configured': 'true'},
        }
        smb_manager = MagicMock()
        smb_manager.list_managed_shares.return_value = [
            {'name': 'backup', 'path': '/media/backup', 'managed': True}
        ]
        self.app.extensions["simple_safer_server"].config_manager = config_manager
        self.app.extensions["simple_safer_server"].smb_manager = smb_manager
        self.app.extensions["simple_safer_server"].runtime = types.SimpleNamespace(
            smtp_config_path=smtp_path
        )

        with self.app.test_client() as client:
            response = client.get('/api/setup/readiness')

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn('data', payload)
        self.assertEqual(payload['data']['status'], 'complete')
        self.assertEqual(payload['data']['completed_required_count'], 5)
        self.assertEqual(
            [item['key'] for item in payload['data']['items']],
            ['storage', 'network_access', 'cloud_backup', 'alerts', 'schedule'],
        )

    def test_format_drive_rejects_non_string_disk(self):
        # JSON clients can send numeric or other non-string values; reject cleanly.
        with self.app.test_client() as client:
            response = client.post('/api/setup/format', json={'disk': 123})

        data = response.get_json()
        self.assertIn('string', data['detail'])

    def test_format_drive_rejects_falsey_non_string_disk(self):
        # Falsey but non-None values (e.g. False, 0) must hit the isinstance check,
        # not the "No disk selected" branch, so the error is accurate.
        with self.app.test_client() as client:
            response = client.post('/api/setup/format', json={'disk': False})

        data = response.get_json()
        self.assertIn('string', data['detail'])

    def test_format_drive_uses_privileged_format_action(self):
        helper = MagicMock()
        helper.run.return_value = types.SimpleNamespace(
            data={
                'disk': '/dev/sdb',
                'partition': '/dev/sdb1',
                'message': 'Successfully formatted /dev/sdb1 as NTFS.',
            }
        )
        self.app.extensions["simple_safer_server"].privileged_actions = helper

        with self.app.test_client() as client:
            response = self._post_format(client, '/dev/sdb')

        self.assertEqual(response.status_code, 200)
        self.assertDataResponse(
            response,
            {
                'result': {
                    'disk': '/dev/sdb',
                    'partition': '/dev/sdb1',
                    'message': 'Successfully formatted /dev/sdb1 as NTFS.',
                }
            },
        )
        helper.run.assert_called_once_with('storage.format', {'disk': '/dev/sdb'})

    def test_format_drive_maps_helper_validation_error(self):
        from simple_safer_server.core.privileged_client import PrivilegedActionClientError

        helper = MagicMock()
        helper.run.side_effect = PrivilegedActionClientError(
            'Invalid disk path: must be a /dev/ device node.',
            exit_code=2,
        )
        self.app.extensions["simple_safer_server"].privileged_actions = helper

        with self.app.test_client() as client:
            response = self._post_format(client, '/tmp/evil')

        self.assertEqual(response.status_code, 400)
        self.assertProblemDetail(response, 'Invalid disk path: must be a /dev/ device node.')
