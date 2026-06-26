import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from simple_safer_server.core.module_lifecycle import (
    module_apply_resources,
    ownership_manifest_for_runtime,
)
from simple_safer_server.core.ownership import OwnershipManifest
from simple_safer_server.modules.file_sharing.module import (
    create_module as create_file_sharing_module,
)
from simple_safer_server.services.user_manager import UserManager, sync_user_to_samba_account


class FakeUserCommandAdapter:
    """Fake OS/user command boundary that only emulates Samba state for tests."""

    def __init__(self):
        self.system_users_set = {"operator"}
        self.created_system_users = []
        self.removed_system_users = []
        self.samba_users_set = set()
        self.removed_users = []
        self.fail_remove = False
        self.fail_sync = False
        self.passwords = {}

    def system_user_exists(self, username):
        return username in self.system_users_set

    def create_system_user(self, username):
        self.system_users_set.add(username)
        self.created_system_users.append(username)

    def samba_users(self):
        # Samba users are tracked in memory so sync behavior can be asserted.
        return list(self.samba_users_set)

    def set_samba_password(self, username, password):
        # Store the latest test password without invoking smbpasswd.
        if self.fail_sync:
            from simple_safer_server.adapters.command_runner import CalledProcessError

            raise CalledProcessError(1, ["smbpasswd", "-s", "-a", username])
        self.samba_users_set.add(username)
        self.passwords[username] = password

    def remove_samba_user(self, username):
        # fail_remove lets deletion tests exercise the CalledProcessError path.
        if self.fail_remove:
            from simple_safer_server.adapters.command_runner import CalledProcessError

            raise CalledProcessError(1, ["smbpasswd", "-x", username])
        self.removed_users.append(username)

    def remove_system_user(self, username):
        self.removed_system_users.append(username)
        self.system_users_set.discard(username)


class UserManagerTests(unittest.TestCase):
    def make_manager(self, is_fake=False):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        # Each test gets a temp config dir and an injected fake adapter so no
        # real OS users or Samba accounts are touched.
        runtime = SimpleNamespace(
            config_dir=Path(temp_dir.name) / "config",
            data_dir=Path(temp_dir.name) / "data",
            is_fake=is_fake,
        )
        adapter = FakeUserCommandAdapter()
        return UserManager(runtime=runtime, command_adapter=adapter), adapter

    def make_manager_with_privileged_actions(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        runtime = SimpleNamespace(
            config_dir=Path(temp_dir.name) / "config",
            data_dir=Path(temp_dir.name) / "data",
            is_fake=False,
        )
        adapter = FakeUserCommandAdapter()
        privileged_actions = SimpleNamespace(run=MagicMock())
        return (
            UserManager(
                runtime=runtime,
                command_adapter=adapter,
                privileged_actions=privileged_actions,
            ),
            adapter,
            privileged_actions,
        )

    def apply_file_sharing(self, manager):
        module = create_file_sharing_module()
        ownership_manifest_for_runtime(manager.runtime).record_module_resources(
            module.slug,
            module_apply_resources(module),
        )

    def test_create_user_defaults_to_non_admin(self):
        manager, _adapter = self.make_manager(is_fake=True)

        success, message = manager.create_user("operator", "OperatorPassw0rd!")

        self.assertTrue(success, message)
        self.assertFalse(manager.users["operator"]["is_admin"])

    def test_create_user_skips_samba_when_file_sharing_is_not_applied(self):
        manager, adapter = self.make_manager()
        adapter.fail_sync = True

        success, message = manager.create_user("operator", "OperatorPassw0rd!")

        self.assertTrue(success, message)
        self.assertIn("operator", manager.users)
        self.assertNotIn("operator", adapter.samba_users_set)

    def test_admin_set_password_syncs_samba_when_file_sharing_is_applied(self):
        manager, adapter = self.make_manager()
        self.apply_file_sharing(manager)
        success, message = manager.create_user("operator", "OperatorPassw0rd!")
        self.assertTrue(success, message)

        success, message = manager.set_password("operator", "NewOperatorPassw0rd!")

        self.assertTrue(success, message)
        self.assertEqual(adapter.passwords["operator"], "NewOperatorPassw0rd!")

    def test_direct_samba_sync_records_new_host_accounts(self):
        manager, adapter = self.make_manager()
        adapter.system_users_set.clear()

        result = sync_user_to_samba_account(
            "backupuser",
            "OperatorPassw0rd!",
            runtime=manager.runtime,
            command_adapter=adapter,
        )

        self.assertTrue(result)
        self.assertEqual(adapter.created_system_users, ["backupuser"])
        self.assertIn("backupuser", adapter.samba_users_set)
        records = OwnershipManifest(manager.runtime.data_dir / "ownership.json").list_records()
        self.assertIn(
            ("file-sharing", "system-user", "backupuser"),
            {(record.module_slug, record.kind, record.identifier) for record in records},
        )
        self.assertIn(
            ("file-sharing", "samba-account", "backupuser"),
            {(record.module_slug, record.kind, record.identifier) for record in records},
        )

    def test_direct_samba_sync_refuses_unmanaged_existing_samba_account(self):
        manager, adapter = self.make_manager()
        adapter.samba_users_set.add("operator")

        result = sync_user_to_samba_account(
            "operator",
            "OperatorPassw0rd!",
            runtime=manager.runtime,
            command_adapter=adapter,
        )

        self.assertFalse(result)
        self.assertNotIn("operator", adapter.passwords)

    def test_delete_user_removes_owned_system_user_and_manifest_records(self):
        manager, adapter = self.make_manager()
        self.apply_file_sharing(manager)
        adapter.system_users_set.clear()

        success, message = manager.create_user("backupuser", "OperatorPassw0rd!")
        self.assertTrue(success, message)

        success, message = manager.delete_user("backupuser")

        self.assertTrue(success, message)
        self.assertEqual(adapter.removed_users, ["backupuser"])
        self.assertEqual(adapter.removed_system_users, ["backupuser"])
        records = OwnershipManifest(manager.runtime.data_dir / "ownership.json").list_records()
        self.assertNotIn(
            ("file-sharing", "system-user", "backupuser"),
            {(record.module_slug, record.kind, record.identifier) for record in records},
        )
        self.assertNotIn(
            ("file-sharing", "samba-account", "backupuser"),
            {(record.module_slug, record.kind, record.identifier) for record in records},
        )

    def test_list_users_excludes_sensitive_state(self):
        manager, _adapter = self.make_manager(is_fake=True)
        success, message = manager.create_user("operator", "OperatorPassw0rd!", is_admin=True)
        self.assertTrue(success, message)

        users = manager.list_users()

        self.assertEqual(len(users), 1)
        user = users[0]
        if user is None:
            self.fail("Expected list_users to return a user dictionary.")
        self.assertEqual(user["username"], "operator")
        self.assertTrue(user["is_admin"])
        self.assertNotIn("password_hash", user)
        self.assertNotIn("failed_attempts", user)

    def test_update_admin_status_persists_role_change(self):
        manager, _adapter = self.make_manager(is_fake=True)
        success, message = manager.create_user("operator", "OperatorPassw0rd!")
        self.assertTrue(success, message)

        success, message = manager.update_admin_status("operator", True)

        self.assertTrue(success, message)
        self.assertTrue(manager.users["operator"]["is_admin"])
        self.assertTrue(manager._load_users()["operator"]["is_admin"])

    def test_update_admin_status_rejects_missing_user(self):
        manager, _adapter = self.make_manager(is_fake=True)

        success, message = manager.update_admin_status("missing", True)

        self.assertFalse(success)
        self.assertEqual(message, "User does not exist")

    def test_create_user_rolls_back_when_samba_sync_fails(self):
        manager, adapter = self.make_manager()
        self.apply_file_sharing(manager)
        adapter.fail_sync = True

        success, message = manager.create_user("operator", "OperatorPassw0rd!")

        self.assertFalse(success)
        self.assertEqual(message, "User creation failed: could not sync with Samba")
        self.assertNotIn("operator", manager.users)

    def test_create_user_uses_privileged_samba_sync_when_available(self):
        manager, adapter, privileged_actions = self.make_manager_with_privileged_actions()
        self.apply_file_sharing(manager)

        success, message = manager.create_user("operator", "OperatorPassw0rd!")

        self.assertTrue(success, message)
        privileged_actions.run.assert_called_once_with(
            "file-sharing.sync-user",
            {"username": "operator", "password": "OperatorPassw0rd!"},
        )
        self.assertNotIn("operator", adapter.samba_users_set)

    def test_create_user_rolls_back_when_save_fails_after_samba_sync(self):
        manager, adapter = self.make_manager()
        self.apply_file_sharing(manager)

        with patch.object(manager, "_save_users", side_effect=OSError("disk full")):
            success, message = manager.create_user("operator", "OperatorPassw0rd!")

        self.assertFalse(success)
        self.assertIn("could not save user record", message)
        self.assertNotIn("operator", manager.users)
        self.assertIn("operator", adapter.samba_users_set)
        self.assertEqual(manager._load_users(), {})

    def test_set_password_keeps_old_hash_when_samba_sync_fails(self):
        manager, adapter = self.make_manager()
        self.apply_file_sharing(manager)
        success, message = manager.create_user("operator", "OperatorPassw0rd!")
        self.assertTrue(success, message)
        original_hash = manager.users["operator"]["password_hash"]
        original_persisted_hash = manager._load_users()["operator"]["password_hash"]
        adapter.fail_sync = True

        success, message = manager.set_password("operator", "NewOperatorPassw0rd!")

        self.assertFalse(success)
        self.assertEqual(message, "Password change failed: could not sync with Samba")
        self.assertEqual(manager.users["operator"]["password_hash"], original_hash)
        self.assertEqual(
            manager._load_users()["operator"]["password_hash"],
            original_persisted_hash,
        )

    def test_delete_user_skips_samba_when_file_sharing_is_not_applied(self):
        manager, adapter = self.make_manager()
        success, message = manager.create_user("operator", "OperatorPassw0rd!")
        self.assertTrue(success, message)
        adapter.fail_remove = True

        success, message = manager.delete_user("operator")

        self.assertTrue(success, message)
        self.assertNotIn("operator", manager.users)
        self.assertEqual(adapter.removed_users, [])

    def test_delete_user_stops_when_samba_removal_fails(self):
        manager, adapter = self.make_manager()
        self.apply_file_sharing(manager)
        success, message = manager.create_user("operator", "OperatorPassw0rd!")
        self.assertTrue(success, message)
        adapter.fail_remove = True

        success, message = manager.delete_user("operator")

        self.assertFalse(success)
        self.assertEqual(message, "Failed to remove user from Samba")
        self.assertIn("operator", manager.users)

    def test_delete_user_uses_privileged_samba_removal_when_available(self):
        manager, _adapter, privileged_actions = self.make_manager_with_privileged_actions()
        self.apply_file_sharing(manager)
        success, message = manager.create_user("operator", "OperatorPassw0rd!")
        self.assertTrue(success, message)
        privileged_actions.run.reset_mock()

        success, message = manager.delete_user("operator")

        self.assertTrue(success, message)
        privileged_actions.run.assert_called_once_with(
            "file-sharing.remove-user",
            {"username": "operator"},
        )
        self.assertNotIn("operator", manager.users)


if __name__ == "__main__":
    unittest.main()
