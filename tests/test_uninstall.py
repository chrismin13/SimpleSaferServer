import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
UNINSTALL_SCRIPT = REPO_ROOT / "uninstall.sh"


class UninstallScriptTests(unittest.TestCase):
    def source_with_samba_dir(self, samba_dir):
        return textwrap.dedent(
            f"""\
            SAMBA_DIR="{samba_dir}"
            source "{UNINSTALL_SCRIPT}"
            """
        )

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

    def test_uninstall_removes_schedule_restore_units_and_helper(self):
        script = UNINSTALL_SCRIPT.read_text()

        self.assertIn('remove_systemd_unit "simple_safer_server_restore_schedules.timer"', script)
        self.assertIn('remove_systemd_unit "simple_safer_server_restore_schedules.service"', script)
        self.assertIn("restore_disabled_timers.py", script)
        self.assertIn('rm -rf "$DATA_DIR"', script)

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

    def test_cleanup_managed_smb_shares_leaves_unmanaged_and_legacy_inline_blocks(self):
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
                    {self.source_with_samba_dir(Path(tempdir))}
                    cleanup_managed_smb_shares
                    """
                )
            )

            content = smb_conf_path.read_text()

        self.assertIn("# BEGIN SimpleSaferServer share: backup", content)
        self.assertIn("[backup]", content)
        self.assertIn("# END SimpleSaferServer share: backup", content)
        self.assertIn("[media]", content)
        self.assertIn("guest ok = yes", content)

    def test_cleanup_managed_smb_shares_removes_sss_include_blocks_and_owned_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            samba_dir = Path(tempdir)
            smb_conf_path = samba_dir / "smb.conf"
            globals_path = samba_dir / "simple_safer_server_globals.conf"
            shares_path = samba_dir / "simple_safer_server_shares.conf"
            globals_path.write_text("map to guest = never\n")
            shares_path.write_text("# managed shares\n")
            smb_conf_path.write_text(
                textwrap.dedent(
                    f"""\
                    [global]
                       workgroup = WORKGROUP
                    # BEGIN SimpleSaferServer global include
                       include = {globals_path}
                    # END SimpleSaferServer global include

                    [media]
                       path = /srv/media

                    # BEGIN SimpleSaferServer shares include
                    include = {shares_path}
                    # END SimpleSaferServer shares include
                    """
                )
            )

            self.run_bash(
                textwrap.dedent(
                    f"""\
                    {self.source_with_samba_dir(samba_dir)}
                    cleanup_managed_smb_shares
                    """
                )
            )

            content = smb_conf_path.read_text()
            globals_exists = globals_path.exists()
            shares_exists = shares_path.exists()

        self.assertIn("[global]", content)
        self.assertIn("[media]", content)
        self.assertNotIn("SimpleSaferServer global include", content)
        self.assertNotIn("SimpleSaferServer shares include", content)
        self.assertFalse(globals_exists)
        self.assertFalse(shares_exists)

    def test_cleanup_managed_smb_shares_deletes_owned_files_when_main_config_missing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            samba_dir = Path(tempdir)
            globals_path = samba_dir / "simple_safer_server_globals.conf"
            shares_path = samba_dir / "simple_safer_server_shares.conf"
            globals_path.write_text("map to guest = never\n")
            shares_path.write_text("# managed shares\n")

            self.run_bash(
                textwrap.dedent(
                    f"""\
                    {self.source_with_samba_dir(samba_dir)}
                    cleanup_managed_smb_shares
                    """
                )
            )

            self.assertFalse(globals_path.exists())
            self.assertFalse(shares_path.exists())

    def test_cleanup_managed_smb_shares_does_not_restart_discovery_services(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            samba_dir = root / "samba"
            fake_bin = root / "bin"
            calls_path = root / "systemctl-calls"
            samba_dir.mkdir()
            fake_bin.mkdir()
            smb_conf_path = samba_dir / "smb.conf"
            smb_conf_path.write_text(
                textwrap.dedent(
                    """\
                    [global]
                       workgroup = WORKGROUP
                    # BEGIN SimpleSaferServer shares include
                    include = /etc/samba/simple_safer_server_shares.conf
                    # END SimpleSaferServer shares include
                    """
                )
            )
            systemctl = fake_bin / "systemctl"
            systemctl.write_text(
                textwrap.dedent(
                    f"""\
                    #!/bin/sh
                    printf '%s\\n' "$*" >> "{calls_path}"
                    exit 0
                    """
                )
            )
            systemctl.chmod(0o755)

            self.run_bash(
                textwrap.dedent(
                    f"""\
                    {self.source_with_samba_dir(samba_dir)}
                    export PATH="{fake_bin}:$PATH"
                    cleanup_managed_smb_shares
                    """
                )
            )

            calls = calls_path.read_text()

        self.assertIn("restart smbd", calls)
        self.assertNotIn("restart nmbd", calls)
        self.assertNotIn("restart wsdd2", calls)

    def test_cleanup_managed_smb_shares_allows_empty_result_when_only_include_blocks_exist(self):
        with tempfile.TemporaryDirectory() as tempdir:
            smb_conf_path = Path(tempdir) / "smb.conf"
            smb_conf_path.write_text(
                textwrap.dedent(
                    """\
                    # BEGIN SimpleSaferServer global include
                       include = /etc/samba/simple_safer_server_globals.conf
                    # END SimpleSaferServer global include

                    # BEGIN SimpleSaferServer shares include
                    include = /etc/samba/simple_safer_server_shares.conf
                    # END SimpleSaferServer shares include
                    """
                )
            )

            self.run_bash(
                textwrap.dedent(
                    f"""\
                    {self.source_with_samba_dir(Path(tempdir))}
                    cleanup_managed_smb_shares
                    """
                )
            )

            content = smb_conf_path.read_text()

        self.assertNotIn("SimpleSaferServer global include", content)
        self.assertNotIn("SimpleSaferServer shares include", content)

    def test_cleanup_managed_smb_shares_rejects_malformed_include_markers(self):
        with tempfile.TemporaryDirectory() as tempdir:
            samba_dir = Path(tempdir)
            smb_conf_path = samba_dir / "smb.conf"
            globals_path = samba_dir / "simple_safer_server_globals.conf"
            shares_path = samba_dir / "simple_safer_server_shares.conf"
            globals_path.write_text("map to guest = never\n")
            shares_path.write_text("# managed shares\n")
            original = textwrap.dedent(
                """\
                [global]
                   workgroup = WORKGROUP

                  # BEGIN SimpleSaferServer global include
                   include = /etc/samba/simple_safer_server_globals.conf

                [media]
                   path = /srv/media
                """
            )
            smb_conf_path.write_text(original)

            result = self.run_bash_raw(
                textwrap.dedent(
                    f"""\
                    {self.source_with_samba_dir(samba_dir)}
                    cleanup_managed_smb_shares
                    """
                )
            )

            content = smb_conf_path.read_text()
            globals_exists = globals_path.exists()
            shares_exists = shares_path.exists()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("markers are malformed", result.stdout)
        self.assertEqual(content, original)
        self.assertFalse(globals_exists)
        self.assertFalse(shares_exists)

    def test_cleanup_managed_smb_shares_restarts_smbd_after_successful_cleanup(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            samba_dir = root / "samba"
            fake_bin = root / "bin"
            calls_path = root / "systemctl-calls"
            samba_dir.mkdir()
            fake_bin.mkdir()
            smb_conf_path = samba_dir / "smb.conf"
            globals_path = samba_dir / "simple_safer_server_globals.conf"
            shares_path = samba_dir / "simple_safer_server_shares.conf"
            globals_path.write_text("map to guest = never\n")
            shares_path.write_text("# managed shares\n")
            smb_conf_path.write_text(
                textwrap.dedent(
                    """\
                    [global]
                       workgroup = WORKGROUP
                    # BEGIN SimpleSaferServer global include
                       include = /etc/samba/simple_safer_server_globals.conf
                    # END SimpleSaferServer global include

                    # BEGIN SimpleSaferServer shares include
                    include = /etc/samba/simple_safer_server_shares.conf
                    # END SimpleSaferServer shares include
                    """
                )
            )
            systemctl = fake_bin / "systemctl"
            systemctl.write_text(
                textwrap.dedent(
                    f"""\
                    #!/bin/sh
                    printf '%s\\n' "$*" >> "{calls_path}"
                    exit 0
                    """
                )
            )
            systemctl.chmod(0o755)

            self.run_bash(
                textwrap.dedent(
                    f"""\
                    {self.source_with_samba_dir(samba_dir)}
                    export PATH="{fake_bin}:$PATH"
                    cleanup_managed_smb_shares
                    """
                )
            )

            calls = calls_path.read_text()

        self.assertIn("restart smbd", calls)
        self.assertNotIn("restart nmbd", calls)
        self.assertNotIn("restart wsdd2", calls)

    def test_cleanup_managed_smb_shares_warns_on_smbd_restart_failure(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            samba_dir = root / "samba"
            fake_bin = root / "bin"
            samba_dir.mkdir()
            fake_bin.mkdir()
            smb_conf_path = samba_dir / "smb.conf"
            globals_path = samba_dir / "simple_safer_server_globals.conf"
            shares_path = samba_dir / "simple_safer_server_shares.conf"
            globals_path.write_text("map to guest = never\n")
            shares_path.write_text("# managed shares\n")
            smb_conf_path.write_text(
                textwrap.dedent(
                    """\
                    [global]
                       workgroup = WORKGROUP
                    # BEGIN SimpleSaferServer shares include
                    include = /etc/samba/simple_safer_server_shares.conf
                    # END SimpleSaferServer shares include
                    """
                )
            )
            systemctl = fake_bin / "systemctl"
            systemctl.write_text(
                textwrap.dedent(
                    """\
                    #!/bin/sh
                    exit 1
                    """
                )
            )
            systemctl.chmod(0o755)

            # Should NOT fail even though smbd restart fails
            result = self.run_bash_raw(
                textwrap.dedent(
                    f"""\
                    {self.source_with_samba_dir(samba_dir)}
                    export PATH="{fake_bin}:$PATH"
                    cleanup_managed_smb_shares
                    """
                )
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn("WARNING", result.stdout)
        self.assertIn("smbd", result.stdout)

    def test_cleanup_managed_smb_shares_malformed_markers_warns_about_broken_includes(self):
        with tempfile.TemporaryDirectory() as tempdir:
            samba_dir = Path(tempdir)
            smb_conf_path = samba_dir / "smb.conf"
            globals_path = samba_dir / "simple_safer_server_globals.conf"
            shares_path = samba_dir / "simple_safer_server_shares.conf"
            globals_path.write_text("map to guest = never\n")
            shares_path.write_text("# managed shares\n")
            smb_conf_path.write_text(
                textwrap.dedent(
                    """\
                    [global]
                       workgroup = WORKGROUP

                      # BEGIN SimpleSaferServer global include
                       include = /etc/samba/simple_safer_server_globals.conf

                    [media]
                       path = /srv/media
                    """
                )
            )

            result = self.run_bash_raw(
                textwrap.dedent(
                    f"""\
                    {self.source_with_samba_dir(samba_dir)}
                    cleanup_managed_smb_shares
                    """
                )
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("simple_safer_server_globals.conf", result.stdout)
        self.assertIn("simple_safer_server_shares.conf", result.stdout)
        self.assertIn("systemctl restart smbd", result.stdout)

    def test_cleanup_managed_smb_shares_removes_empty_legacy_backup_directory(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            samba_dir = root / "samba"
            samba_dir.mkdir()
            backup_dir = samba_dir / "backups"
            backup_dir.mkdir()
            smb_conf_path = samba_dir / "smb.conf"
            smb_conf_path.write_text(
                textwrap.dedent(
                    """\
                    [global]
                       workgroup = WORKGROUP
                    # BEGIN SimpleSaferServer shares include
                    include = /etc/samba/simple_safer_server_shares.conf
                    # END SimpleSaferServer shares include
                    """
                )
            )

            self.run_bash(
                textwrap.dedent(
                    f"""\
                    {self.source_with_samba_dir(samba_dir)}
                    cleanup_managed_smb_shares
                    """
                )
            )

            self.assertFalse(backup_dir.exists())

    def test_cleanup_managed_smb_shares_leaves_nonempty_legacy_backup_directory(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            samba_dir = root / "samba"
            samba_dir.mkdir()
            backup_dir = samba_dir / "backups"
            backup_dir.mkdir()
            (backup_dir / "smb.conf.backup.20250101_120000").write_text("[global]\n")
            smb_conf_path = samba_dir / "smb.conf"
            smb_conf_path.write_text(
                textwrap.dedent(
                    """\
                    [global]
                       workgroup = WORKGROUP
                    # BEGIN SimpleSaferServer shares include
                    include = /etc/samba/simple_safer_server_shares.conf
                    # END SimpleSaferServer shares include
                    """
                )
            )

            self.run_bash(
                textwrap.dedent(
                    f"""\
                    {self.source_with_samba_dir(samba_dir)}
                    cleanup_managed_smb_shares
                    """
                )
            )

            self.assertTrue(backup_dir.exists())
            self.assertTrue((backup_dir / "smb.conf.backup.20250101_120000").exists())

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

    def test_uninstall_piped_to_bash_does_not_raise_unbound_variable(self):
        # Piping the script to bash (simulating curl ... | bash) should not crash
        # with 'BASH_SOURCE[0]: unbound variable' error under 'set -u'.
        # Since it is run as non-root in tests, it should fail at the root check
        # in main(), returning exit code 1 and the expected error message.
        script_content = UNINSTALL_SCRIPT.read_text(encoding="utf-8")
        result = subprocess.run(
            ["bash"],
            input=script_content,
            capture_output=True,
            text=True,
            env={"SSS_FORCE_NON_ROOT_CHECK": "true"},
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Please run as root", result.stderr or result.stdout)
        self.assertNotIn("unbound variable", result.stderr)


if __name__ == "__main__":
    unittest.main()
