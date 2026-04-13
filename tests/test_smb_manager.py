import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import smb_manager


class SMBManagerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.runtime = SimpleNamespace(
            samba_dir=self.root / "samba",
            samba_backup_dir=self.root / "samba-backups",
            is_fake=True,
        )
        self.runtime.samba_dir.mkdir(parents=True, exist_ok=True)
        self.runtime.samba_backup_dir.mkdir(parents=True, exist_ok=True)
        self.fake_state = SimpleNamespace(
            set_smb_services=lambda smbd, nmbd: None,
            get_smb_services=lambda: {"smbd": "active", "nmbd": "active"},
        )

        patcher = patch.object(smb_manager, "get_fake_state", return_value=self.fake_state)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.manager = smb_manager.SMBManager(runtime=self.runtime)

    def _write_conf(self, content):
        (self.runtime.samba_dir / "smb.conf").write_text(content)

    def test_list_managed_and_unmanaged_shares_in_mixed_config(self):
        self._write_conf(
            "\n".join(
                [
                    "[global]",
                    "   workgroup = WORKGROUP",
                    "",
                    "# BEGIN SimpleSaferServer share: backup",
                    "[backup]",
                    "   path = /media/backup",
                    "   writeable = Yes",
                    "   comment = Managed backup share",
                    "   valid users = admin",
                    "# END SimpleSaferServer share: backup",
                    "",
                    "[media]",
                    "   path = /srv/media",
                    "   guest ok = yes",
                    "",
                ]
            )
        )

        managed = self.manager.list_managed_shares()
        unmanaged = self.manager.list_unmanaged_shares()

        self.assertEqual([share["name"] for share in managed], ["backup"])
        self.assertEqual([share["name"] for share in unmanaged], ["media"])
        self.assertEqual(managed[0]["path"], "/media/backup")

    def test_malformed_managed_marker_raises_clear_error(self):
        self._write_conf(
            "\n".join(
                [
                    "[global]",
                    "   workgroup = WORKGROUP",
                    "",
                    "# BEGIN SimpleSaferServer share: backup",
                    "[backup]",
                    "   path = /media/backup",
                    "",
                ]
            )
        )

        with self.assertRaises(smb_manager.SMBConfigError):
            self.manager.list_managed_shares()

    def test_create_managed_share_writes_wrapped_block(self):
        share_path = self.root / "share"
        share_path.mkdir()

        self.manager.create_managed_share(
            "backup",
            str(share_path),
            writable=True,
            comment="Managed by tests",
            valid_users=["admin"],
        )

        content = (self.runtime.samba_dir / "smb.conf").read_text()
        self.assertIn("# BEGIN SimpleSaferServer share: backup", content)
        self.assertIn("[backup]", content)
        self.assertIn(f"   path = {share_path}", content)
        self.assertIn("# END SimpleSaferServer share: backup", content)

    def test_update_managed_share_preserves_unmanaged_block(self):
        old_path = self.root / "old-share"
        old_path.mkdir()
        new_path = self.root / "new-share"
        new_path.mkdir()
        self._write_conf(
            "\n".join(
                [
                    "[global]",
                    "   workgroup = WORKGROUP",
                    "",
                    "[media]",
                    "   path = /srv/media",
                    "   guest ok = yes",
                    "",
                    "# BEGIN SimpleSaferServer share: backup",
                    "[backup]",
                    f"   path = {old_path}",
                    "   writeable = Yes",
                    "   comment = Old comment",
                    "   valid users = admin",
                    "# END SimpleSaferServer share: backup",
                    "",
                ]
            )
        )

        self.manager.update_managed_share(
            "backup",
            "backup",
            str(new_path),
            writable=False,
            comment="Updated comment",
            valid_users=["admin", "operator"],
        )

        content = (self.runtime.samba_dir / "smb.conf").read_text()
        self.assertIn("[media]\n   path = /srv/media\n   guest ok = yes\n", content)
        self.assertIn(f"   path = {new_path}", content)
        self.assertIn("   writeable = No", content)
        self.assertIn("   valid users = admin operator", content)

    def test_delete_managed_share_only_removes_owned_block(self):
        self._write_conf(
            "\n".join(
                [
                    "[global]",
                    "   workgroup = WORKGROUP",
                    "",
                    "# BEGIN SimpleSaferServer share: backup",
                    "[backup]",
                    "   path = /media/backup",
                    "   writeable = Yes",
                    "# END SimpleSaferServer share: backup",
                    "",
                    "[media]",
                    "   path = /srv/media",
                    "",
                ]
            )
        )

        self.manager.delete_managed_share("backup")

        content = (self.runtime.samba_dir / "smb.conf").read_text()
        self.assertNotIn("[backup]", content)
        self.assertIn("[media]", content)

    def test_ensure_default_backup_share_updates_existing_managed_share(self):
        old_path = self.root / "old-backup"
        old_path.mkdir()
        new_path = self.root / "new-backup"
        new_path.mkdir()
        self._write_conf(
            "\n".join(
                [
                    "# BEGIN SimpleSaferServer share: backup",
                    "[backup]",
                    f"   path = {old_path}",
                    "   writeable = Yes",
                    "   comment = Original",
                    "   valid users = admin",
                    "# END SimpleSaferServer share: backup",
                    "",
                ]
            )
        )

        self.manager.ensure_default_backup_share(str(new_path), "admin")

        share = self.manager.get_managed_share("backup")
        self.assertEqual(share["path"], str(new_path))
        self.assertEqual(share["valid_users"], ["admin"])

    def test_ensure_default_backup_share_rejects_unmanaged_backup_share(self):
        share_path = self.root / "backup"
        share_path.mkdir()
        self._write_conf(
            "\n".join(
                [
                    "[backup]",
                    f"   path = {share_path}",
                    "   guest ok = yes",
                    "",
                ]
            )
        )

        with self.assertRaisesRegex(ValueError, "unmanaged Samba share named 'backup'"):
            self.manager.ensure_default_backup_share(str(share_path), "admin")

    def test_create_managed_share_rejects_comment_with_newline_injection(self):
        share_path = self.root / "share-with-comment"
        share_path.mkdir()

        with self.assertRaisesRegex(ValueError, "Share comment contains unsupported control characters"):
            self.manager.create_managed_share(
                "backup",
                str(share_path),
                comment="Looks fine\nguest ok = yes",
                valid_users=["admin"],
            )

    def test_create_managed_share_rejects_non_directory_path(self):
        file_path = self.root / "not-a-directory"
        file_path.write_text("hello")

        with self.assertRaisesRegex(ValueError, "must be an existing directory"):
            self.manager.create_managed_share("backup", str(file_path))

    def test_create_managed_share_rejects_whitespace_in_valid_users(self):
        share_path = self.root / "share-with-users"
        share_path.mkdir()

        with self.assertRaisesRegex(ValueError, "Share usernames may only contain"):
            self.manager.create_managed_share(
                "backup",
                str(share_path),
                valid_users=["admin user"],
            )

    def test_restart_failure_restores_previous_live_config(self):
        runtime = SimpleNamespace(
            samba_dir=self.root / "real-samba",
            samba_backup_dir=self.root / "real-samba-backups",
            is_fake=False,
        )
        runtime.samba_dir.mkdir(parents=True, exist_ok=True)
        runtime.samba_backup_dir.mkdir(parents=True, exist_ok=True)
        manager = smb_manager.SMBManager(runtime=runtime)
        live_path = runtime.samba_dir / "smb.conf"
        original_content = "[global]\n   workgroup = WORKGROUP\n"
        live_path.write_text(original_content)

        share_path = self.root / "real-share"
        share_path.mkdir()
        backup_path = runtime.samba_backup_dir / "smb.conf.backup.test"

        def fake_backup():
            backup_path.write_text(live_path.read_text())
            return str(backup_path)

        with patch.object(manager, "_create_backup", side_effect=fake_backup):
            with patch.object(manager, "_validate_smb_conf_candidate", return_value=None):
                with patch.object(manager, "_restart_services", side_effect=[False, True]):
                    with self.assertRaisesRegex(RuntimeError, "Failed to restart SMB services"):
                        manager.create_managed_share("backup", str(share_path))

        self.assertEqual(live_path.read_text(), original_content)


if __name__ == "__main__":
    unittest.main()
