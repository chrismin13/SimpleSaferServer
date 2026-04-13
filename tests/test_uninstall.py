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


if __name__ == "__main__":
    unittest.main()
