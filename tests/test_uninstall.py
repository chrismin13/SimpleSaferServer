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
        data_dir = Path(samba_dir) / "sss-data"
        data_dir.mkdir(parents=True, exist_ok=True)
        ownership_manifest = data_dir / "ownership.json"
        ownership_manifest.write_text(
            json.dumps(
                {
                    "version": 1,
                    "resources": [
                        {
                            "module_slug": "file-sharing",
                            "kind": "config-file",
                            "identifier": str(Path(samba_dir) / "simple_safer_server_globals.conf"),
                            "reason": "Test-owned Samba globals include.",
                        },
                        {
                            "module_slug": "file-sharing",
                            "kind": "config-file",
                            "identifier": str(Path(samba_dir) / "simple_safer_server_shares.conf"),
                            "reason": "Test-owned Samba shares include.",
                        },
                        {
                            "module_slug": "file-sharing",
                            "kind": "samba-account",
                            "identifier": "alice",
                            "reason": "Test-owned Samba account.",
                        },
                        {
                            "module_slug": "file-sharing",
                            "kind": "system-user",
                            "identifier": "bob",
                            "reason": "Test-owned Linux user.",
                        },
                    ],
                }
            )
        )
        return textwrap.dedent(
            f"""\
            SAMBA_DIR="{samba_dir}"
            DATA_DIR="{data_dir}"
            OWNERSHIP_MANIFEST="{ownership_manifest}"
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

    def test_collect_owned_samba_accounts_reads_manifest(self):
        with tempfile.TemporaryDirectory() as tempdir:
            output = self.run_bash(
                textwrap.dedent(
                    f"""\
                    {self.source_with_samba_dir(Path(tempdir))}
                    collect_owned_samba_accounts
                    """
                )
            )

        self.assertEqual(output.strip().splitlines(), ["alice"])

    def test_collect_owned_accounts_fails_on_invalid_manifest(self):
        with tempfile.TemporaryDirectory() as tempdir:
            data_dir = Path(tempdir) / "sss-data"
            data_dir.mkdir()
            ownership_manifest = data_dir / "ownership.json"
            ownership_manifest.write_text("{ definitely not valid json")

            result = self.run_bash_raw(
                textwrap.dedent(
                    f"""\
                    source "{UNINSTALL_SCRIPT}"
                    OWNERSHIP_MANIFEST="{ownership_manifest}"
                    collect_owned_samba_accounts
                    """
                )
            )

        self.assertNotEqual(result.returncode, 0)

    def test_remove_manifest_owned_accounts_removes_only_manifest_accounts(self):
        with tempfile.TemporaryDirectory() as tempdir:
            log_path = Path(tempdir) / "commands.log"

            output = self.run_bash(
                textwrap.dedent(
                    f"""\
                    {self.source_with_samba_dir(Path(tempdir))}
                    smbpasswd() {{ echo "smbpasswd:$*" >> "{log_path}"; }}
                    userdel() {{ echo "userdel:$*" >> "{log_path}"; }}
                    remove_manifest_owned_accounts >/dev/null
                    cat "{log_path}"
                    """
                )
            )

        self.assertEqual(output.strip().splitlines(), ["smbpasswd:-x alice", "userdel:bob"])

    def test_uninstall_removes_app_data_directory(self):
        script = UNINSTALL_SCRIPT.read_text()

        self.assertIn('rm -rf "$DATA_DIR"', script)

    def test_uninstall_removes_helper_sudoers_and_owned_service_identity(self):
        script = UNINSTALL_SCRIPT.read_text()

        self.assertIn('SUDOERS_FILE="/etc/sudoers.d/simple-safer-server"', script)
        self.assertIn('rm -f "$SUDOERS_FILE"', script)
        self.assertIn('SERVICE_USER_MARKER="$DATA_DIR/.sss-user-created"', script)
        self.assertIn('SERVICE_GROUP_MARKER="$DATA_DIR/.sss-group-created"', script)
        self.assertIn('userdel "$APP_USER"', script)
        self.assertIn('groupdel "$APP_GROUP"', script)

    def test_uninstaller_does_not_manage_hostnames(self):
        script = UNINSTALL_SCRIPT.read_text()

        self.assertNotIn("managed_hostname_summary", script)
        self.assertNotIn("hostname_managed", script)

    def test_remove_managed_fstab_entries_only_removes_tagged_lines(self):
        with tempfile.TemporaryDirectory() as tempdir:
            fstab_path = Path(tempdir) / "fstab"
            fstab_path.write_text(
                textwrap.dedent(
                    """\
                    # comment
                    UUID=keep /mnt/keep ext4 defaults 0 2
                    UUID=drop /media/backup ntfs-3g defaults,nofail 0 0 # SimpleSaferServer managed backup drive
                    UUID=unmanaged /media/other ntfs-3g defaults 0 0 # SimpleSaferServer
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
        self.assertIn("UUID=unmanaged /media/other", content)

    def test_cleanup_managed_smb_shares_leaves_unowned_inline_blocks(self):
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

    def test_cleanup_managed_smb_shares_leaves_files_without_ownership_manifest(self):
        with tempfile.TemporaryDirectory() as tempdir:
            samba_dir = Path(tempdir)
            data_dir = samba_dir / "missing-data"
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
                # END SimpleSaferServer global include
                """
            )
            smb_conf_path.write_text(original)

            output = self.run_bash(
                textwrap.dedent(
                    f"""\
                    SAMBA_DIR="{samba_dir}"
                    DATA_DIR="{data_dir}"
                    OWNERSHIP_MANIFEST="{data_dir / "ownership.json"}"
                    source "{UNINSTALL_SCRIPT}"
                    cleanup_managed_smb_shares
                    """
                )
            )

            self.assertIn("No File Sharing ownership records found", output)
            self.assertEqual(smb_conf_path.read_text(), original)
            self.assertTrue(globals_path.exists())
            self.assertTrue(shares_path.exists())

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

    def test_uninstaller_removes_worker_service_and_sss_cli_wrapper(self):
        text = UNINSTALL_SCRIPT.read_text(encoding="utf-8")
        scripts_block = text[text.index("SCRIPT_FILES=(") : text.index(")", text.index("SCRIPT_FILES=("))]

        self.assertIn("simple-safer-server-worker.service", text)
        self.assertIn("sss", scripts_block)
        self.assertIn("sss-helper", scripts_block)
        self.assertNotIn("backup_cloud.sh", scripts_block)
        self.assertNotIn("check_mount.sh", scripts_block)
        self.assertNotIn("ddns_update.py", scripts_block)


if __name__ == "__main__":
    unittest.main()
