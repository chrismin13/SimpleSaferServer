import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
UNINSTALL_SCRIPT = REPO_ROOT / "uninstall.sh"


class UninstallScriptTests(unittest.TestCase):
    def run_bash(self, snippet):
        result = subprocess.run(
            ["bash", "-lc", snippet],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr or result.stdout)
        return result.stdout

    def run_bash_raw(self, snippet):
        return subprocess.run(
            ["bash", "-lc", snippet],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

    def test_collect_samba_users_reads_current_users_json_shape(self):
        with tempfile.TemporaryDirectory() as tempdir:
            users_path = Path(tempdir) / "users.json"
            users_path.write_text(json.dumps({"alice": {"is_admin": True}, "bob": {"is_admin": False}}))

            output = self.run_bash(
                textwrap.dedent(
                    f"""\
                    source "{UNINSTALL_SCRIPT}"
                    USERS_FILE="{users_path}"
                    collect_samba_users
                    """
                )
            )

        self.assertEqual(output.strip().splitlines(), ["alice", "bob"])

    def test_collect_samba_users_fails_on_invalid_json(self):
        with tempfile.TemporaryDirectory() as tempdir:
            users_path = Path(tempdir) / "users.json"
            users_path.write_text("{ definitely not valid json")

            result = self.run_bash_raw(
                textwrap.dedent(
                    f"""\
                    source "{UNINSTALL_SCRIPT}"
                    USERS_FILE="{users_path}"
                    collect_samba_users
                    """
                )
            )

        self.assertNotEqual(result.returncode, 0)

    def test_apt_updates_were_managed_detects_managed_config(self):
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "config.conf"
            config_path.write_text(
                textwrap.dedent(
                    """\
                    [apt_updates]
                    managed = true
                    """
                )
            )

            self.run_bash(
                textwrap.dedent(
                    f"""\
                    source "{UNINSTALL_SCRIPT}"
                    CONFIG_FILE="{config_path}"
                    apt_updates_were_managed
                    """
                )
            )

    def test_apt_updates_were_managed_ignores_unmanaged_config(self):
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "config.conf"
            config_path.write_text(
                textwrap.dedent(
                    """\
                    [apt_updates]
                    managed = false
                    """
                )
            )

            result = self.run_bash_raw(
                textwrap.dedent(
                    f"""\
                    source "{UNINSTALL_SCRIPT}"
                    CONFIG_FILE="{config_path}"
                    apt_updates_were_managed
                    """
                )
            )

        self.assertNotEqual(result.returncode, 0)

    def test_apt_updates_were_managed_ignores_other_sections(self):
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "config.conf"
            config_path.write_text(
                textwrap.dedent(
                    """\
                    [other]
                    managed = true

                    [apt_updates]
                    update_package_lists = true
                    """
                )
            )

            result = self.run_bash_raw(
                textwrap.dedent(
                    f"""\
                    source "{UNINSTALL_SCRIPT}"
                    CONFIG_FILE="{config_path}"
                    apt_updates_were_managed
                    """
                )
            )

        self.assertNotEqual(result.returncode, 0)

    def test_remove_managed_fstab_entries_only_removes_tagged_lines(self):
        with tempfile.TemporaryDirectory() as tempdir:
            fstab_path = Path(tempdir) / "fstab"
            fstab_path.write_text(
                textwrap.dedent(
                    """\
                    # comment
                    UUID=keep /mnt/keep ext4 defaults 0 2
                    UUID=drop /media/backup ntfs-3g defaults,nofail 0 0 # SimpleSaferServer managed backup drive
                    UUID=legacy /media/legacy ntfs-3g defaults 0 0 # SimpleSaferServer
                    """
                )
            )

            self.run_bash(
                textwrap.dedent(
                    f"""\
                    source "{UNINSTALL_SCRIPT}"
                    remove_managed_fstab_entries "{fstab_path}"
                    """
                )
            )

            content = fstab_path.read_text()

        self.assertIn("UUID=keep /mnt/keep ext4 defaults 0 2", content)
        self.assertNotIn("UUID=drop /media/backup", content)
        self.assertNotIn("UUID=legacy /media/legacy", content)

    def test_cleanup_managed_smb_shares_leaves_unmanaged_blocks(self):
        with tempfile.TemporaryDirectory() as tempdir:
            smb_conf_path = Path(tempdir) / "smb.conf"
            smb_conf_path.write_text(
                textwrap.dedent(
                    """\
                    [global]
                       workgroup = WORKGROUP

                    # BEGIN SimpleSaferServer share: backup
                    [backup]
                       path = /media/backup
                    # END SimpleSaferServer share: backup

                    [media]
                       path = /srv/media
                       guest ok = yes
                    """
                )
            )

            self.run_bash(
                textwrap.dedent(
                    f"""\
                    source "{UNINSTALL_SCRIPT}"
                    SMB_CONF="{smb_conf_path}"
                    cleanup_managed_smb_shares
                    """
                )
            )

            content = smb_conf_path.read_text()

        self.assertNotIn("[backup]", content)
        self.assertIn("[media]", content)
        self.assertIn("guest ok = yes", content)

    def test_cleanup_managed_smb_shares_allows_empty_result_when_only_managed_blocks_exist(self):
        with tempfile.TemporaryDirectory() as tempdir:
            smb_conf_path = Path(tempdir) / "smb.conf"
            smb_conf_path.write_text(
                textwrap.dedent(
                    """\
                    # BEGIN SimpleSaferServer share: backup
                    [backup]
                       path = /media/backup
                    # END SimpleSaferServer share: backup
                    """
                )
            )

            self.run_bash(
                textwrap.dedent(
                    f"""\
                    source "{UNINSTALL_SCRIPT}"
                    SMB_CONF="{smb_conf_path}"
                    cleanup_managed_smb_shares
                    """
                )
            )

            content = smb_conf_path.read_text()

        self.assertEqual(content, "")

    def test_cleanup_managed_smb_shares_rejects_malformed_markers(self):
        with tempfile.TemporaryDirectory() as tempdir:
            smb_conf_path = Path(tempdir) / "smb.conf"
            original = textwrap.dedent(
                """\
                [global]
                   workgroup = WORKGROUP

                  # BEGIN SimpleSaferServer share: backup
                [backup]
                   path = /media/backup
                  # END SimpleSaferServer share: media
                """
            )
            smb_conf_path.write_text(original)

            result = self.run_bash_raw(
                textwrap.dedent(
                    f"""\
                    source "{UNINSTALL_SCRIPT}"
                    SMB_CONF="{smb_conf_path}"
                    cleanup_managed_smb_shares
                    """
                )
            )

            content = smb_conf_path.read_text()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("markers are malformed", result.stdout)
        self.assertEqual(content, original)


if __name__ == "__main__":
    unittest.main()
