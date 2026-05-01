import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from simple_safer_server.services.user_manager import UserManager


class FakeUserCommandAdapter:
    """Fake OS/user command boundary that only emulates Samba state for tests."""

    def __init__(self):
        self.samba_users_set = set()
        self.removed_users = []
        self.fail_remove = False
        self.passwords = {}

    def system_user_exists(self, username):
        # Tests avoid real system user lookups; every requested user exists.
        return True

    def create_system_user(self, username):
        # System user creation is a no-op because tests only assert manager behavior.
        return None

    def samba_users(self):
        # Samba users are tracked in memory so sync behavior can be asserted.
        return list(self.samba_users_set)

    def set_samba_password(self, username, password):
        # Store the latest test password without invoking smbpasswd.
        self.samba_users_set.add(username)
        self.passwords[username] = password

    def remove_samba_user(self, username):
        # fail_remove lets deletion tests exercise the CalledProcessError path.
        if self.fail_remove:
            from simple_safer_server.adapters.command_runner import CalledProcessError

            raise CalledProcessError(1, ["smbpasswd", "-x", username])
        self.removed_users.append(username)


class UserManagerTests(unittest.TestCase):
    def make_manager(self, is_fake=False):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        # Each test gets a temp config dir and an injected fake adapter so no
        # real OS users or Samba accounts are touched.
        runtime = SimpleNamespace(config_dir=Path(temp_dir.name), is_fake=is_fake)
        adapter = FakeUserCommandAdapter()
        return UserManager(runtime=runtime, command_adapter=adapter), adapter

    def test_create_user_defaults_to_non_admin(self):
        manager, _adapter = self.make_manager(is_fake=True)

        success, message = manager.create_user("operator", "OperatorPassw0rd!")

        self.assertTrue(success, message)
        self.assertFalse(manager.users["operator"]["is_admin"])

    def test_admin_set_password_syncs_samba(self):
        manager, adapter = self.make_manager()
        success, message = manager.create_user("operator", "OperatorPassw0rd!")
        self.assertTrue(success, message)

        success, message = manager.set_password("operator", "NewOperatorPassw0rd!")

        self.assertTrue(success, message)
        self.assertEqual(adapter.passwords["operator"], "NewOperatorPassw0rd!")

    def test_delete_user_stops_when_samba_removal_fails(self):
        manager, adapter = self.make_manager()
        success, message = manager.create_user("operator", "OperatorPassw0rd!")
        self.assertTrue(success, message)
        adapter.fail_remove = True

        success, message = manager.delete_user("operator")

        self.assertFalse(success)
        self.assertEqual(message, "Failed to remove user from Samba")
        self.assertIn("operator", manager.users)


if __name__ == "__main__":
    unittest.main()
