import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from simple_safer_server.adapters.command_runner import CalledProcessError
from simple_safer_server.legacy import migration
from simple_safer_server.services.smb_manager import SMBManager
from simple_safer_server.services.user_manager import UserManager


class FailingSyncUserCommandAdapter:
    """Test adapter that rejects Samba password writes without touching the OS."""

    def system_user_exists(self, username):
        return True

    def create_system_user(self, username):
        return None

    def samba_users(self):
        return ["admin"]

    def set_samba_password(self, username, password):
        raise CalledProcessError(1, ["smbpasswd", "-s", "-a", username])

    def remove_samba_user(self, username):
        return None


class MigrationCommandHandlingTests(unittest.TestCase):
    def test_existing_admin_update_keeps_old_hash_when_samba_sync_fails(self):
        with tempfile.TemporaryDirectory() as tempdir:
            runtime = SimpleNamespace(config_dir=Path(tempdir), is_fake=True)
            user_manager = UserManager(
                runtime=runtime, command_adapter=FailingSyncUserCommandAdapter()
            )
            success, message = user_manager.create_user("admin", "OriginalPassw0rd!", is_admin=True)
            self.assertTrue(success, message)
            original_hash = user_manager.users["admin"]["password_hash"]

            # The production Runtime exposes is_fake as a read-only derived
            # property; this test double is mutable so the same manager can
            # seed JSON in fake mode and then exercise the real sync failure.
            runtime.is_fake = False

            with self.assertRaises(migration.MigrationError):
                migration._ensure_admin_user(user_manager, "admin", "NewPassw0rd!")

            self.assertEqual(user_manager.users["admin"]["password_hash"], original_hash)
            self.assertEqual(
                user_manager._load_users()["admin"]["password_hash"],
                original_hash,
            )

    def test_configure_backup_share_treats_missing_systemctl_as_nonfatal(self):
        # The migration helper only touches this small manager surface; the
        # cast keeps the test double focused without constructing real system
        # service managers in a command-failure unit test.
        smb_manager = cast(
            SMBManager,
            SimpleNamespace(
                runtime=SimpleNamespace(is_fake=False),
                ensure_default_backup_share=lambda *args, **kwargs: None,
            ),
        )
        user_manager = cast(
            UserManager,
            SimpleNamespace(
                users={"admin": {}},
                reload_users=lambda: None,
                user_exists_in_samba=lambda username: True,
            ),
        )

        with patch.object(
            migration.command_runner,
            "run",
            side_effect=FileNotFoundError("systemctl"),
        ):
            migration._configure_backup_share(
                smb_manager,
                user_manager,
                mount_point="/media/backup",
                admin_username="admin",
            )

    def test_restart_web_service_converts_missing_systemctl_to_migration_error(self):
        runtime = SimpleNamespace(is_fake=False)

        with patch.object(
            migration.command_runner,
            "run",
            side_effect=FileNotFoundError("systemctl"),
        ):
            with self.assertRaises(migration.MigrationError):
                migration._restart_web_service(runtime)


if __name__ == "__main__":
    unittest.main()
