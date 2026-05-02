import unittest
from types import SimpleNamespace
from unittest.mock import patch

from simple_safer_server.legacy import migration


class MigrationCommandHandlingTests(unittest.TestCase):
    def test_configure_backup_share_treats_missing_systemctl_as_nonfatal(self):
        smb_manager = SimpleNamespace(
            runtime=SimpleNamespace(is_fake=False),
            ensure_default_backup_share=lambda *args, **kwargs: None,
        )
        user_manager = SimpleNamespace(
            users={"admin": {}},
            reload_users=lambda: None,
            user_exists_in_samba=lambda username: True,
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
