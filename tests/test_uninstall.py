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
            users_path.write_text(
                json.dumps({"alice": {"is_admin": True}, "bob": {"is_admin": False}})
            )

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

    def test_livepatch_was_managed_detects_managed_config(self):
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "config.conf"
            config_path.write_text(
                textwrap.dedent(
                    """\
                    [system_updates]
                    livepatch_managed = true
                    """
                )
            )

            self.run_bash(
                textwrap.dedent(
                    f"""\
                    source "{UNINSTALL_SCRIPT}"
                    CONFIG_FILE="{config_path}"
                    livepatch_was_managed
                    """
                )
            )

    def test_livepatch_was_managed_ignores_missing_or_false_config(self):
        with tempfile.TemporaryDirectory() as tempdir:
            missing_path = Path(tempdir) / "missing.conf"
            false_path = Path(tempdir) / "config.conf"
            false_path.write_text(
                textwrap.dedent(
                    """\
                    [system_updates]
                    livepatch_managed = false
                    """
                )
            )

            missing_result = self.run_bash_raw(
                textwrap.dedent(
                    f"""\
                    source "{UNINSTALL_SCRIPT}"
                    CONFIG_FILE="{missing_path}"
                    livepatch_was_managed
                    """
                )
            )
            false_result = self.run_bash_raw(
                textwrap.dedent(
                    f"""\
                    source "{UNINSTALL_SCRIPT}"
                    CONFIG_FILE="{false_path}"
                    livepatch_was_managed
                    """
                )
            )

        self.assertNotEqual(missing_result.returncode, 0)
        self.assertNotEqual(false_result.returncode, 0)

    def test_livepatch_was_managed_ignores_other_managed_sections(self):
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "config.conf"
            config_path.write_text(
                textwrap.dedent(
                    """\
                    [apt_updates]
                    managed = true

                    [other]
                    livepatch_managed = true
                    """
                )
            )

            result = self.run_bash_raw(
                textwrap.dedent(
                    f"""\
                    source "{UNINSTALL_SCRIPT}"
                    CONFIG_FILE="{config_path}"
                    livepatch_was_managed
                    """
                )
            )

        self.assertNotEqual(result.returncode, 0)

    def test_managed_hostname_summary_reads_hostname_metadata(self):
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "config.conf"
            config_path.write_text(
                textwrap.dedent(
                    """\
                    [system]
                    hostname_managed = true
                    original_hostname = oldbox
                    applied_hostname = newbox
                    """
                )
            )

            output = self.run_bash(
                textwrap.dedent(
                    f"""\
                    source "{UNINSTALL_SCRIPT}"
                    CONFIG_FILE="{config_path}"
                    managed_hostname_summary
                    """
                )
            )

        lines = output.strip().splitlines()
        self.assertIn("original=oldbox", lines)
        self.assertIn("applied=newbox", lines)
        self.assertTrue(any(line.startswith("current=") for line in lines))

    def test_managed_hostname_summary_ignores_unmanaged_config(self):
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "config.conf"
            config_path.write_text(
                textwrap.dedent(
                    """\
                    [system]
                    hostname_managed = false
                    original_hostname = oldbox
                    applied_hostname = newbox
                    """
                )
            )

            output = self.run_bash(
                textwrap.dedent(
                    f"""\
                    source "{UNINSTALL_SCRIPT}"
                    CONFIG_FILE="{config_path}"
                    managed_hostname_summary
                    """
                )
            )

        self.assertEqual(output, "")

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

    def test_remove_git_safe_directory_removes_only_matching_entries(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            fake_bin = root / "bin"
            config_path = root / "gitconfig"
            fake_bin.mkdir()
            git = fake_bin / "git"
            git.write_text(
                textwrap.dedent(
                    f"""\
                    #!/bin/sh
                    export GIT_CONFIG_SYSTEM="{config_path}"
                    exec /usr/bin/git "$@"
                    """
                )
            )
            git.chmod(0o755)
            env_prefix = f'export PATH="{fake_bin}:$PATH"'
            subprocess.run(
                [
                    "bash",
                    "-lc",
                    textwrap.dedent(
                        f"""\
                        {env_prefix}
                        git config --system --add safe.directory /opt/SimpleSaferServer
                        git config --system --add safe.directory /srv/other
                        git config --system --add safe.directory /opt/SimpleSaferServer
                        """
                    ),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.run_bash(
                textwrap.dedent(
                    f"""\
                    source "{UNINSTALL_SCRIPT}"
                    {env_prefix}
                    remove_git_safe_directory /opt/SimpleSaferServer
                    """
                )
            )

            remaining = subprocess.run(
                [
                    "bash",
                    "-lc",
                    f'{env_prefix}\ngit config --system --get-all safe.directory',
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        self.assertEqual(remaining.stdout.strip().splitlines(), ["/srv/other"])


if __name__ == "__main__":
    unittest.main()
