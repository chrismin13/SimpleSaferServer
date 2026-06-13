import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from simple_safer_server.services import smb_manager


class FakeSmbCommandAdapter:
    def __init__(
        self,
        *,
        validation_returncode=0,
        validation_returncodes=None,
        unit_statuses=None,
        restart_failures=None,
        reload_failures=None,
    ):
        self.validation_returncode = validation_returncode
        self.validation_returncodes = list(validation_returncodes or [])
        self.validated_paths = []
        self.validation_cwds = []
        self.validated_candidate_texts = []
        self.unit_statuses = unit_statuses or {}
        self.restart_failures = set(restart_failures or [])
        self.restarted_units = []
        self.reload_failures = set(reload_failures or [])
        self.reloaded_units = []

    def validate_config(self, validator, candidate_path, cwd=None):
        self.validated_paths.append(Path(candidate_path))
        self.validation_cwds.append(Path(cwd) if cwd is not None else None)
        candidate_text = Path(candidate_path).read_text(encoding="utf-8")
        self.validated_candidate_texts.append(candidate_text)
        returncode = (
            self.validation_returncodes.pop(0)
            if self.validation_returncodes
            else self.validation_returncode
        )
        return SimpleNamespace(
            returncode=returncode,
            stdout=candidate_text if returncode == 0 else "",
            stderr="invalid shares file" if returncode else "",
        )

    def unit_status(self, unit_name):
        if unit_name not in self.unit_statuses:
            raise RuntimeError(f"{unit_name} status unavailable")
        return self.unit_statuses[unit_name]

    def restart_unit(self, unit_name):
        self.restarted_units.append(unit_name)
        if unit_name in self.restart_failures:
            raise smb_manager.CalledProcessError(1, ["systemctl", "restart", unit_name])

    def reload_config(self):
        self.reloaded_units.append("smbd")
        if "smbd" in self.reload_failures:
            raise smb_manager.CalledProcessError(1, ["smbcontrol", "smbd", "reload-config"])


class SMBManagerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.runtime = SimpleNamespace(
            samba_dir=self.root / "samba",
            volatile_dir=self.root / "run",
            is_fake=True,
        )
        self.runtime.samba_dir.mkdir(parents=True, exist_ok=True)
        self.runtime.volatile_dir.mkdir(parents=True, exist_ok=True)
        self.fake_state = SimpleNamespace(
            set_smb_services=lambda smbd, nmbd, wsdd2="active": None,
            get_smb_services=lambda: {"smbd": "active", "nmbd": "active", "wsdd2": "active"},
        )

        patcher = patch.object(smb_manager, "get_fake_state", return_value=self.fake_state)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.adapter = FakeSmbCommandAdapter()
        self.manager = smb_manager.SMBManager(
            runtime=self.runtime,
            command_adapter=self.adapter,
        )

    def _write_conf(self, content):
        (self.runtime.samba_dir / "smb.conf").write_text(content)

    def _write_shares(self, content):
        (self.runtime.samba_dir / "simple_safer_server_shares.conf").write_text(content)

    def test_list_managed_shares_reads_sss_shares_file_not_main_config_markers(self):
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
        self._write_shares(
            "\n".join(
                [
                    "# SimpleSaferServer-managed Samba shares",
                    "[photos]",
                    "   path = /srv/photos",
                    "   writeable = Yes",
                    "   comment = SSS file share",
                    "   valid users = admin",
                    "",
                ]
            )
        )

        managed = self.manager.list_managed_shares()
        unmanaged = self.manager.list_unmanaged_shares()

        self.assertEqual([share["name"] for share in managed], ["photos"])
        self.assertEqual([share["name"] for share in unmanaged], ["backup", "media"])
        self.assertEqual(managed[0]["path"], "/srv/photos")

    def test_malformed_sss_shares_file_raises_clear_error(self):
        self._write_shares(
            "\n".join(
                [
                    "[backup]",
                    "   path = /media/backup",
                    "[backup]",
                    "   path = /srv/duplicate",
                ]
            )
        )

        with self.assertRaisesRegex(smb_manager.SMBConfigError, "unsupported or malformed"):
            self.manager.list_managed_shares()

    def test_unsupported_directives_in_sss_shares_file_do_not_crash_listing(self):
        self._write_shares(
            "\n".join(
                [
                    "[backup]",
                    "   path = /media/backup",
                    "   veto files = /*.tmp/",
                    "   writeable = Yes",
                    "   comment = Manual extra directive",
                    "",
                ]
            )
        )

        shares = self.manager.list_managed_shares()

        self.assertEqual(shares[0]["name"], "backup")
        self.assertEqual(shares[0]["path"], "/media/backup")

    def test_create_managed_share_writes_sss_shares_file_and_validates_layout(self):
        share_path = self.root / "share"
        share_path.mkdir()

        self.manager.create_managed_share(
            "backup",
            str(share_path),
            writable=True,
            comment="Managed by tests",
            valid_users=["admin"],
        )

        content = (self.runtime.samba_dir / "simple_safer_server_shares.conf").read_text()
        self.assertNotIn("# BEGIN SimpleSaferServer share: backup", content)
        self.assertIn("[backup]", content)
        self.assertIn(f"   path = {share_path}", content)
        self.assertTrue((self.runtime.samba_dir / "simple_safer_server_globals.conf").exists())
        self.assertEqual(len(self.adapter.validated_paths), 3)

    def test_list_unmanaged_shares_uses_stripped_effective_config_candidate(self):
        self._write_conf(
            "\n".join(
                [
                    "[global]",
                    "   workgroup = WORKGROUP",
                    "# BEGIN SimpleSaferServer global include",
                    "   include = /etc/samba/simple_safer_server_globals.conf",
                    "# END SimpleSaferServer global include",
                    "",
                    "[homes]",
                    "   browseable = no",
                    "",
                    "include = /etc/samba/site-shares.conf",
                    "",
                    "# BEGIN SimpleSaferServer shares include",
                    "include = /etc/samba/simple_safer_server_shares.conf",
                    "# END SimpleSaferServer shares include",
                    "",
                ]
            )
        )

        captured = {}

        def fake_effective_config(_validator, candidate_path, cwd=None):
            captured["candidate_path"] = Path(candidate_path)
            captured["cwd"] = Path(cwd) if cwd is not None else None
            captured["candidate_text"] = Path(candidate_path).read_text(encoding="utf-8")
            return SimpleNamespace(
                returncode=0,
                stdout="\n".join(
                    [
                        "[global]",
                        "[homes]",
                        "[printers]",
                        "[print$]",
                        "[media]",
                        "   path = /srv/media",
                        "[backup]",
                        "   path = /srv/backup",
                        "",
                    ]
                ),
                stderr="",
            )

        with patch.object(self.adapter, "validate_config", side_effect=fake_effective_config):
            unmanaged = self.manager.list_unmanaged_shares()

        self.assertEqual([share["name"] for share in unmanaged], ["media", "backup"])
        candidate_path = captured["candidate_path"]
        self.assertEqual(candidate_path.parent, self.runtime.volatile_dir)
        self.assertEqual(captured["cwd"], self.runtime.samba_dir)
        self.assertFalse(candidate_path.exists())
        self.assertIn("include = /etc/samba/site-shares.conf", captured["candidate_text"])
        self.assertNotIn("SimpleSaferServer global include", captured["candidate_text"])
        self.assertNotIn("SimpleSaferServer shares include", captured["candidate_text"])

    def test_unmanaged_inspection_fails_closed_for_malformed_include_markers(self):
        self._write_conf(
            "\n".join(
                [
                    "[global]",
                    "# BEGIN SimpleSaferServer shares include",
                    "include = /etc/samba/simple_safer_server_shares.conf",
                    "[media]",
                    "   path = /srv/media",
                    "",
                ]
            )
        )

        with self.assertRaisesRegex(smb_manager.SMBConfigError, "marker block is malformed"):
            self.manager.list_unmanaged_shares()

    def test_unmanaged_inspection_fails_closed_when_effective_config_fails(self):
        self._write_conf("[global]\n[media]\n   path = /srv/media\n")
        manager = smb_manager.SMBManager(
            runtime=self.runtime,
            command_adapter=FakeSmbCommandAdapter(validation_returncode=1),
        )

        with self.assertRaisesRegex(smb_manager.SMBConfigError, "effective Samba config"):
            manager.list_unmanaged_shares()

    def test_update_managed_share_preserves_unmanaged_block(self):
        old_path = self.root / "old-share"
        old_path.mkdir()
        new_path = self.root / "new-share"
        new_path.mkdir()
        self._write_conf("[media]\n   path = /srv/media\n   guest ok = yes\n")
        self._write_shares(
            "\n".join(
                [
                    "[backup]",
                    f"   path = {old_path}",
                    "   writeable = Yes",
                    "   comment = Old comment",
                    "   valid users = admin",
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

        content = (self.runtime.samba_dir / "simple_safer_server_shares.conf").read_text()
        self.assertNotIn("[media]", content)
        self.assertIn(f"   path = {new_path}", content)
        self.assertIn("   writeable = No", content)
        self.assertIn("   valid users = admin operator", content)

    def test_delete_managed_share_only_removes_owned_block(self):
        self._write_conf("[media]\n   path = /srv/media\n")
        self._write_shares(
            "\n".join(
                [
                    "[backup]",
                    "   path = /media/backup",
                    "   writeable = Yes",
                    "",
                ]
            )
        )

        self.manager.delete_managed_share("backup")

        content = (self.runtime.samba_dir / "simple_safer_server_shares.conf").read_text()
        self.assertNotIn("[backup]", content)
        self.assertIn("[media]", (self.runtime.samba_dir / "smb.conf").read_text())

    def test_delete_managed_share_does_not_inspect_unmanaged_effective_config(self):
        self._write_conf("[global]\n[media]\n   path = /srv/media\n")
        self._write_shares("[backup]\n   path = /media/backup\n")

        with patch.object(
            self.manager,
            "_inspect_unmanaged_effective_shares",
            side_effect=AssertionError("delete should only read the owned shares file"),
        ):
            self.manager.delete_managed_share("backup")

        content = (self.runtime.samba_dir / "simple_safer_server_shares.conf").read_text()
        self.assertNotIn("[backup]", content)

    def test_update_managed_share_without_rename_ignores_effective_self_conflict(self):
        old_path = self.root / "old-backup"
        old_path.mkdir()
        new_path = self.root / "new-backup"
        new_path.mkdir()
        self._write_shares(
            "\n".join(
                [
                    "[backup]",
                    f"   path = {old_path}",
                    "   writeable = Yes",
                    "",
                ]
            )
        )

        effective_self = smb_manager.ParsedShare(
            name="backup",
            managed=False,
            path="/media/backup",
        )
        with patch.object(
            self.manager,
            "_inspect_unmanaged_effective_shares",
            return_value=[effective_self],
        ):
            self.manager.update_managed_share("backup", "backup", str(new_path))

        content = (self.runtime.samba_dir / "simple_safer_server_shares.conf").read_text()
        self.assertIn(f"   path = {new_path}", content)

    def test_ensure_default_backup_share_updates_existing_managed_share(self):
        old_path = self.root / "old-backup"
        old_path.mkdir()
        new_path = self.root / "new-backup"
        new_path.mkdir()
        self._write_shares(
            "\n".join(
                [
                    "[backup]",
                    f"   path = {old_path}",
                    "   writeable = Yes",
                    "   comment = Original",
                    "   valid users = admin",
                    "",
                ]
            )
        )

        self.manager.ensure_default_backup_share(str(new_path), "admin")

        share = self.manager.get_managed_share("backup")
        self.assertEqual(share["path"], str(new_path))
        self.assertEqual(share["valid_users"], ["admin"])

    def test_ensure_default_backup_share_uses_short_unmanaged_backup_conflict(self):
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

        with self.assertRaisesRegex(
            ValueError,
            'Samba share "backup" already exists. Rename or remove it, then retry.',
        ):
            self.manager.ensure_default_backup_share(str(share_path), "admin")

    def test_create_managed_share_rejects_unmanaged_conflict_from_main_config(self):
        share_path = self.root / "new-backup"
        share_path.mkdir()
        self._write_conf("[backup]\n   path = /srv/existing\n")

        with self.assertRaisesRegex(ValueError, "already exists"):
            self.manager.create_managed_share("backup", str(share_path))

    def test_update_managed_share_rejects_rename_to_unmanaged_conflict(self):
        old_path = self.root / "old-backup"
        old_path.mkdir()
        new_path = self.root / "new-backup"
        new_path.mkdir()
        self._write_conf("[media]\n   path = /srv/media\n")
        self._write_shares(f"[backup]\n   path = {old_path}\n")

        with self.assertRaisesRegex(ValueError, "already exists"):
            self.manager.update_managed_share("backup", "media", str(new_path))

    def test_validation_failure_rolls_back_sss_shares_file(self):
        share_path = self.root / "validated-share"
        share_path.mkdir()
        self._write_shares("# existing shares\n")
        manager = smb_manager.SMBManager(
            runtime=self.runtime,
            command_adapter=FakeSmbCommandAdapter(validation_returncodes=[0, 0, 1]),
        )

        with self.assertRaisesRegex(smb_manager.SMBConfigError, "validation failed"):
            manager.create_managed_share("backup", str(share_path))

        self.assertEqual(
            (self.runtime.samba_dir / "simple_safer_server_shares.conf").read_text(),
            "# existing shares\n",
        )

    def test_create_managed_share_rejects_comment_with_newline_injection(self):
        share_path = self.root / "share-with-comment"
        share_path.mkdir()

        with self.assertRaisesRegex(
            ValueError, "Share comment contains unsupported control characters"
        ):
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

    def test_create_managed_share_rejects_string_valid_users_input(self):
        share_path = self.root / "share-string-users"
        share_path.mkdir()

        with self.assertRaisesRegex(ValueError, "valid_users must be a sequence of usernames"):
            self.manager.create_managed_share(
                "backup",
                str(share_path),
                valid_users="admin",
            )

    def test_get_share_users_does_not_inspect_effective_config_for_managed_share(self):
        """Managed-share user reads must not call Effective Config inspection.

        The share is found in the owned file, so inspection is unnecessary and
        must not be triggered.
        """
        share_path = self.root / "managed-share"
        share_path.mkdir()
        self._write_shares(
            "\n".join(
                [
                    "[backup]",
                    f"   path = {share_path}",
                    "   writeable = Yes",
                    "   valid users = admin operator",
                    "",
                ]
            )
        )

        with patch.object(
            self.manager,
            "_inspect_unmanaged_effective_shares",
            side_effect=AssertionError("should not inspect effective config for a managed share"),
        ):
            users = self.manager.get_share_users("backup")

        self.assertEqual(users, ["admin", "operator"])

    def test_update_share_users_does_not_inspect_effective_config_for_managed_share(self):
        """Managed-share user updates must not call Effective Config inspection.

        The share is found in the owned file and the name is unchanged, so
        inspection is unnecessary and must not be triggered.
        """
        share_path = self.root / "managed-share"
        share_path.mkdir()
        self._write_shares(
            "\n".join(
                [
                    "[backup]",
                    f"   path = {share_path}",
                    "   writeable = Yes",
                    "   comment = Test share",
                    "   valid users = admin",
                    "",
                ]
            )
        )

        with patch.object(
            self.manager,
            "_inspect_unmanaged_effective_shares",
            side_effect=AssertionError("should not inspect effective config for a managed share"),
        ):
            self.manager.update_share_users("backup", ["admin", "operator"])

        content = (self.runtime.samba_dir / "simple_safer_server_shares.conf").read_text()
        self.assertIn("valid users = admin operator", content)

    def test_get_share_users_rejects_unmanaged_share(self):
        share_path = self.root / "unmanaged-share"
        share_path.mkdir()
        self._write_conf(
            "\n".join(
                [
                    "[media]",
                    f"   path = {share_path}",
                    "   guest ok = yes",
                    "",
                ]
            )
        )

        with self.assertRaisesRegex(ValueError, "is not managed by SimpleSaferServer"):
            self.manager.get_share_users("media")

    def test_get_share_users_uses_existing_snapshot_without_second_lookup(self):
        share_path = self.root / "managed-share"
        share_path.mkdir()
        self._write_shares(
            "\n".join(
                [
                    "[backup]",
                    f"   path = {share_path}",
                    "   writeable = Yes",
                    "   comment = Managed backup share",
                    "   valid users = admin",
                    "",
                ]
            )
        )

        # This guards the helper against reloading the config after it has
        # already validated ownership from a consistent snapshot.
        with patch.object(
            self.manager,
            "get_managed_share",
            side_effect=AssertionError("unexpected second lookup"),
        ):
            self.assertEqual(self.manager.get_share_users("backup"), ["admin"])

    def test_restart_failure_restores_previous_sss_shares_file(self):
        share_path = self.root / "real-share"
        share_path.mkdir()
        self._write_shares("# original shares\n")

        with patch.object(self.manager, "_restart_services", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "Failed to restart SMB services"):
                self.manager.create_managed_share("backup", str(share_path))

        self.assertEqual(
            (self.runtime.samba_dir / "simple_safer_server_shares.conf").read_text(),
            "# original shares\n",
        )

    def test_publish_failure_restarts_smbd_after_restoring_previous_shares_file(self):
        self.runtime.is_fake = False
        adapter = FakeSmbCommandAdapter(validation_returncodes=[1])
        manager = smb_manager.SMBManager(runtime=self.runtime, command_adapter=adapter)
        self._write_conf("[global]\n")
        self._write_shares("# original shares\n")

        with patch.object(smb_manager.os, "chown"):
            with self.assertRaisesRegex(smb_manager.SMBConfigError, "validation failed"):
                manager._commit_sss_shares_file("# broken publish\n")

        self.assertEqual(
            (self.runtime.samba_dir / "simple_safer_server_shares.conf").read_text(),
            "# original shares\n",
        )
        self.assertEqual(adapter.restarted_units, ["smbd"])

    def test_publish_failure_reports_rollback_restart_failure(self):
        self.runtime.is_fake = False
        adapter = FakeSmbCommandAdapter(
            validation_returncodes=[1],
            restart_failures={"smbd"},
        )
        manager = smb_manager.SMBManager(runtime=self.runtime, command_adapter=adapter)
        self._write_conf("[global]\n")
        self._write_shares("# original shares\n")

        with patch.object(smb_manager.os, "chown"):
            with self.assertRaisesRegex(
                smb_manager.SMBOperationError,
                "share update failed and rollback could not restart smbd",
            ):
                manager._commit_sss_shares_file("# broken publish\n")

        self.assertEqual(
            (self.runtime.samba_dir / "simple_safer_server_shares.conf").read_text(),
            "# original shares\n",
        )
        self.assertEqual(adapter.restarted_units, ["smbd"])

    def test_status_includes_wsdd2_and_reports_missing_unit_as_unavailable(self):
        self.runtime.is_fake = False
        manager = smb_manager.SMBManager(
            runtime=self.runtime,
            command_adapter=FakeSmbCommandAdapter(
                unit_statuses={"smbd": "active", "nmbd": "active"}
            ),
        )

        self.assertEqual(
            manager.get_service_status(),
            {"smbd": "active", "nmbd": "active", "wsdd2": "unavailable"},
        )

    def test_restart_services_attempts_all_three_units(self):
        self.runtime.is_fake = False
        adapter = FakeSmbCommandAdapter()
        manager = smb_manager.SMBManager(runtime=self.runtime, command_adapter=adapter)

        self.assertTrue(manager.restart_services())
        self.assertEqual(adapter.restarted_units, ["smbd", "nmbd", "wsdd2"])

    def test_restart_services_fails_when_smbd_restart_fails(self):
        self.runtime.is_fake = False
        adapter = FakeSmbCommandAdapter(restart_failures={"smbd"})
        manager = smb_manager.SMBManager(runtime=self.runtime, command_adapter=adapter)

        self.assertFalse(manager.restart_services())
        self.assertEqual(adapter.restarted_units, ["smbd"])

    def test_restart_services_allows_discovery_restart_failures(self):
        self.runtime.is_fake = False
        adapter = FakeSmbCommandAdapter(restart_failures={"nmbd", "wsdd2"})
        manager = smb_manager.SMBManager(runtime=self.runtime, command_adapter=adapter)

        self.assertTrue(manager.restart_services())
        self.assertEqual(adapter.restarted_units, ["smbd", "nmbd", "wsdd2"])

    def test_reload_or_restart_smbd_reloads_when_active(self):
        self.runtime.is_fake = False
        adapter = FakeSmbCommandAdapter(unit_statuses={"smbd": "active"})
        manager = smb_manager.SMBManager(runtime=self.runtime, command_adapter=adapter)

        self.assertTrue(manager._reload_or_restart_smbd())
        self.assertEqual(adapter.reloaded_units, ["smbd"])
        self.assertEqual(adapter.restarted_units, [])

    def test_reload_or_restart_smbd_restarts_when_inactive(self):
        self.runtime.is_fake = False
        adapter = FakeSmbCommandAdapter(unit_statuses={"smbd": "inactive"})
        manager = smb_manager.SMBManager(runtime=self.runtime, command_adapter=adapter)

        self.assertTrue(manager._reload_or_restart_smbd())
        self.assertEqual(adapter.reloaded_units, [])
        self.assertEqual(adapter.restarted_units, ["smbd"])

    def test_reload_or_restart_smbd_restarts_when_reload_fails(self):
        self.runtime.is_fake = False
        adapter = FakeSmbCommandAdapter(
            unit_statuses={"smbd": "active"},
            reload_failures={"smbd"},
        )
        manager = smb_manager.SMBManager(runtime=self.runtime, command_adapter=adapter)

        self.assertTrue(manager._reload_or_restart_smbd())
        # Reload was attempted, but failed, so we fall back to restart
        self.assertEqual(adapter.reloaded_units, ["smbd"])
        self.assertEqual(adapter.restarted_units, ["smbd"])

    def test_parse_smb_conf_does_not_treat_marker_comments_as_share_boundaries(self):
        """_parse_smb_conf should parse through old marker-like comments without
        treating them as share block terminators. The method is used to parse
        testparm output which never contains markers, but this confirms the
        legacy break logic is gone."""
        content = "\n".join(
            [
                "[media]",
                "   path = /srv/media",
                "# BEGIN SimpleSaferServer share: media",
                "   writeable = Yes",
                "",
                "[photos]",
                "   path = /srv/photos",
                "",
            ]
        )

        _, shares = self.manager._parse_smb_conf(content)

        self.assertEqual(len(shares), 2)
        self.assertEqual(shares[0].name, "media")
        self.assertTrue(shares[0].writable)
        self.assertEqual(shares[1].name, "photos")

    def test_dead_inline_managed_share_methods_are_removed(self):
        """The old marker-based managed-share machinery should not exist on
        SMBManager. These were replaced by the file-path ownership model."""
        self.assertFalse(hasattr(self.manager, '_create_backup'))
        self.assertFalse(hasattr(self.manager, '_write_smb_conf'))
        self.assertFalse(hasattr(self.manager, '_validate_smb_conf_candidate'))
        self.assertFalse(hasattr(self.manager, '_restore_smb_conf_backup'))
        self.assertFalse(hasattr(self.manager, '_commit_smb_conf'))
        self.assertFalse(hasattr(self.manager, 'backup_dir'))

    def test_dead_marker_constants_are_removed(self):
        """The old marker constants should not exist in the module."""
        self.assertFalse(hasattr(smb_manager, 'MANAGED_SHARE_BEGIN_PREFIX'))
        self.assertFalse(hasattr(smb_manager, 'MANAGED_SHARE_END_PREFIX'))

    def test_get_share_users_raises_not_found_when_share_missing_everywhere(self):
        """A share that exists neither in the owned file nor in unmanaged config
        should produce a generic 'not found' error."""
        self._write_shares("")
        self._write_conf("[global]\n   workgroup = WORKGROUP\n")

        with self.assertRaisesRegex(ValueError, "not found"):
            self.manager.get_share_users("nonexistent")

    def test_get_share_users_raises_not_found_when_inspection_also_fails(self):
        """When the share is not in the owned file and effective config inspection
        also fails, fall back to a generic 'not found' error."""
        self._write_shares("")

        with patch.object(
            self.manager,
            "_inspect_unmanaged_effective_shares",
            side_effect=smb_manager.SMBConfigError("broken include"),
        ):
            with self.assertRaisesRegex(ValueError, "not found"):
                self.manager.get_share_users("nonexistent")


if __name__ == "__main__":
    unittest.main()
