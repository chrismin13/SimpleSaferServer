import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "install.sh"


class InstallPreflightTests(unittest.TestCase):
    def installer_function(self, name):
        text = INSTALL_SCRIPT.read_text()
        start = text.index(f"{name}() {{")
        end = text.index("\n}\n\n", start) + len("\n}\n")
        return text[start:end]

    def run_preflight(self, os_release_text, *args, fake_commands="apt-get,dpkg,systemctl"):
        with tempfile.TemporaryDirectory() as temp_dir:
            os_release_path = Path(temp_dir) / "os-release"
            os_release_path.write_text(textwrap.dedent(os_release_text))
            env = {
                **os.environ,
                "SSS_INSTALLER_PREFLIGHT_ONLY": "1",
                "SSS_INSTALLER_TEST_COMMANDS": fake_commands,
                "SSS_INSTALLER_TEST_SYSTEMD": "1",
                "SSS_OS_RELEASE_PATH": str(os_release_path),
            }
            return subprocess.run(
                ["bash", str(INSTALL_SCRIPT), *args],
                cwd=str(REPO_ROOT),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

    def test_debian_direct_passes(self):
        result = self.run_preflight(
            """
            ID=debian
            VERSION_ID="13"
            PRETTY_NAME="Debian GNU/Linux 13 (trixie)"
            """
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("Install platform preflight passed", result.stdout)

    def test_ubuntu_direct_passes(self):
        result = self.run_preflight(
            """
            ID=ubuntu
            VERSION_ID="24.04"
            PRETTY_NAME="Ubuntu 24.04 LTS"
            """
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("Ubuntu 24.04 LTS", result.stdout)

    def test_older_platform_warns_but_passes(self):
        result = self.run_preflight(
            """
            ID=debian
            VERSION_ID="10"
            PRETTY_NAME="Debian GNU/Linux 10 (buster)"
            """
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("older OS compatibility platform", result.stdout)

    def test_armhf_platform_is_rejected(self):
        result = self.run_preflight(
            """
            ID=debian
            VERSION_ID="13"
            PRETTY_NAME="Debian GNU/Linux 13 (trixie)"
            """,
            fake_commands="apt-get,dpkg,systemctl",
        )
        # The default test host architecture should pass; this keeps the arch
        # override test below focused on the unsupported userspace.
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

        with tempfile.TemporaryDirectory() as temp_dir:
            os_release_path = Path(temp_dir) / "os-release"
            os_release_path.write_text(
                textwrap.dedent(
                    """
                    ID=debian
                    VERSION_ID="13"
                    PRETTY_NAME="Debian GNU/Linux 13 (trixie)"
                    """
                )
            )
            env = {
                **os.environ,
                "SSS_INSTALLER_PREFLIGHT_ONLY": "1",
                "SSS_INSTALLER_TEST_COMMANDS": "apt-get,dpkg,systemctl",
                "SSS_INSTALLER_TEST_SYSTEMD": "1",
                "SSS_INSTALLER_TEST_ARCH": "armhf",
                "SSS_OS_RELEASE_PATH": str(os_release_path),
            }
            armhf_result = subprocess.run(
                ["bash", str(INSTALL_SCRIPT)],
                cwd=str(REPO_ROOT),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(armhf_result.returncode, 0)
        self.assertIn("Unsupported 32-bit ARM architecture", armhf_result.stdout)

    def test_linux_mint_style_derivative_warns_but_passes(self):
        result = self.run_preflight(
            """
            ID=linuxmint
            ID_LIKE="ubuntu debian"
            VERSION_ID="22"
            PRETTY_NAME="Linux Mint 22"
            """
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("Debian/Ubuntu-family derivative", result.stdout)

    def test_debian_derivative_warns_but_passes(self):
        result = self.run_preflight(
            """
            ID=raspbian
            ID_LIKE=debian
            VERSION_ID="12"
            PRETTY_NAME="Raspberry Pi OS"
            """
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("Debian/Ubuntu-family derivative", result.stdout)

    def test_non_debian_family_blocks_by_default(self):
        result = self.run_preflight(
            """
            ID=fedora
            VERSION_ID="42"
            PRETTY_NAME="Fedora Linux 42"
            """
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unsupported OS family", result.stdout)

    def test_non_debian_family_override_passes(self):
        result = self.run_preflight(
            """
            ID=fedora
            VERSION_ID="42"
            PRETTY_NAME="Fedora Linux 42"
            """,
            "--unsupported-os-ok",
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("continuing because --unsupported-os-ok was set", result.stdout)

    def test_missing_required_tool_blocks(self):
        result = self.run_preflight(
            """
            ID=debian
            VERSION_ID="13"
            PRETTY_NAME="Debian GNU/Linux 13 (trixie)"
            """,
            fake_commands="apt-get,dpkg",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing required host tools", result.stdout)
        self.assertIn("systemctl", result.stdout)

    def test_systemctl_without_systemd_blocks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            os_release_path = Path(temp_dir) / "os-release"
            os_release_path.write_text(
                """
                ID=debian
                VERSION_ID="13"
                PRETTY_NAME="Debian GNU/Linux 13 (trixie)"
                """
            )
            env = {
                **os.environ,
                "SSS_INSTALLER_PREFLIGHT_ONLY": "1",
                "SSS_INSTALLER_TEST_COMMANDS": "apt-get,dpkg,systemctl",
                "SSS_INSTALLER_TEST_SYSTEMD": "0",
                "SSS_OS_RELEASE_PATH": str(os_release_path),
            }

            result = subprocess.run(
                ["bash", str(INSTALL_SCRIPT)],
                cwd=str(REPO_ROOT),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "systemd does not appear to be running as the host init system", result.stdout
        )

    def uv_helper_functions(self):
        return "\n".join(
            [
                self.installer_function("uv_version_number"),
                self.installer_function("version_at_least"),
                self.installer_function("ensure_uv"),
            ]
        )

    def test_ensure_uv_uses_existing_uv_when_it_meets_minimum_version(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            existing_bin = root / "existing-bin"
            existing_bin.mkdir()
            (existing_bin / "uv").write_text('#!/bin/sh\necho "uv 0.11.16"\n')
            (existing_bin / "uv").chmod(0o755)
            calls_path = root / "calls.log"

            snippet = textwrap.dedent(
                f"""\
                set -e
                {self.uv_helper_functions()}
                RED=""; GREEN=""; YELLOW=""; NC=""
                MIN_UV_VERSION="0.11.13"
                UV_INSTALL_DIR="{root / "install-bin"}"
                UV_INSTALL_URL="https://astral.sh/uv/install.sh"
                export PATH="{existing_bin}:$PATH"
                curl() {{
                  printf 'curl %s\\n' "$*" >> "{calls_path}"
                  return 42
                }}
                ensure_uv
                command -v uv
                uv --version
                """
            )

            result = subprocess.run(
                ["bash", "-lc", snippet],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn(str(existing_bin / "uv"), result.stdout)
            self.assertIn("uv 0.11.16", result.stdout)
            self.assertFalse(calls_path.exists())

    def test_ensure_uv_installs_latest_when_existing_uv_is_too_old(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_bin = root / "old-bin"
            install_bin = root / "install-bin"
            old_bin.mkdir()
            install_bin.mkdir()
            (old_bin / "uv").write_text('#!/bin/sh\necho "uv 0.10.9"\n')
            (old_bin / "uv").chmod(0o755)
            calls_path = root / "calls.log"

            snippet = textwrap.dedent(
                f"""\
                set -e
                {self.uv_helper_functions()}
                RED=""; GREEN=""; YELLOW=""; NC=""
                MIN_UV_VERSION="0.11.13"
                UV_INSTALL_DIR="{install_bin}"
                UV_INSTALL_URL="https://astral.sh/uv/install.sh"
                export PATH="{old_bin}:$PATH"
                curl() {{
                  printf 'curl %s\\n' "$*" >> "{calls_path}"
                  output_path="${{@: -1}}"
                  {{
                    printf '%s\\n' 'mkdir -p "$UV_INSTALL_DIR"'
                    printf '%s\\n' 'cat > "$UV_INSTALL_DIR/uv" <<'"'"'UVBIN'"'"''
                    printf '%s\\n' '#!/bin/sh'
                    printf '%s\\n' 'echo "uv 0.11.21"'
                    printf '%s\\n' 'UVBIN'
                    printf '%s\\n' 'chmod +x "$UV_INSTALL_DIR/uv"'
                  }} > "$output_path"
                }}
                ensure_uv
                command -v uv
                uv --version
                """
            )

            result = subprocess.run(
                ["bash", "-lc", snippet],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn(str(install_bin / "uv"), result.stdout)
            self.assertIn("uv 0.11.21", result.stdout)
            self.assertIn("curl -fLsS https://astral.sh/uv/install.sh", calls_path.read_text())

    def test_script_install_loop_skips_same_app_destination(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scripts_dir = root / "scripts"
            bin_dir = root / "bin"
            scripts_dir.mkdir()
            bin_dir.mkdir()
            script = scripts_dir / "app_update.sh"
            script.write_text("#!/bin/bash\necho app\n")
            py_script = scripts_dir / "app_update.py"
            py_script.write_text("#!/usr/bin/env python3\nprint('app')\n")

            snippet = textwrap.dedent(
                f"""\
                set -e
                {self.installer_function("same_file")}
                {self.installer_function("copy_unless_same_file")}
                SCRIPTS_DIR="{scripts_dir}"
                BIN_DIR="{bin_dir}"
                cd "{root}"
                for script in scripts/*.sh scripts/*.py; do
                  script_name="$(basename "$script")"
                  app_script_path="$SCRIPTS_DIR/$script_name"
                  bin_script_path="$BIN_DIR/$script_name"
                  if ! same_file "$script" "$app_script_path"; then
                    cp "$script" "$app_script_path"
                    chmod +x "$app_script_path"
                  fi
                  copy_unless_same_file "$script" "$bin_script_path"
                  chmod +x "$bin_script_path"
                done
                """
            )

            result = subprocess.run(
                ["bash", "-lc", snippet],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertFalse(os.access(script, os.X_OK))
            self.assertFalse(os.access(py_script, os.X_OK))
            self.assertEqual((bin_dir / "app_update.sh").read_text(), "#!/bin/bash\necho app\n")
            self.assertTrue(os.access(bin_dir / "app_update.sh", os.X_OK))
            self.assertTrue(os.access(bin_dir / "app_update.py", os.X_OK))

    def test_script_install_loop_preserves_app_script_modes_from_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_dir = root / "source" / "scripts"
            app_scripts_dir = root / "app" / "scripts"
            bin_dir = root / "bin"
            source_dir.mkdir(parents=True)
            app_scripts_dir.mkdir(parents=True)
            bin_dir.mkdir()
            script = source_dir / "app_update.sh"
            py_script = source_dir / "app_update.py"
            script.write_text("#!/bin/bash\necho app\n")
            py_script.write_text("#!/usr/bin/env python3\nprint('app')\n")

            snippet = textwrap.dedent(
                f"""\
                set -e
                {self.installer_function("same_file")}
                {self.installer_function("copy_unless_same_file")}
                SCRIPTS_DIR="{app_scripts_dir}"
                BIN_DIR="{bin_dir}"
                cd "{root / "source"}"
                for script in scripts/*.sh scripts/*.py; do
                  script_name="$(basename "$script")"
                  app_script_path="$SCRIPTS_DIR/$script_name"
                  bin_script_path="$BIN_DIR/$script_name"
                  if ! same_file "$script" "$app_script_path"; then
                    cp "$script" "$app_script_path"
                  fi
                  copy_unless_same_file "$script" "$bin_script_path"
                  chmod +x "$bin_script_path"
                done
                """
            )

            result = subprocess.run(
                ["bash", "-lc", snippet],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertFalse(os.access(app_scripts_dir / "app_update.sh", os.X_OK))
            self.assertFalse(os.access(app_scripts_dir / "app_update.py", os.X_OK))
            self.assertTrue(os.access(bin_dir / "app_update.sh", os.X_OK))
            self.assertTrue(os.access(bin_dir / "app_update.py", os.X_OK))

    def test_git_safe_directory_helper_adds_system_entry_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake_bin = root / "bin"
            config_path = root / "gitconfig"
            calls_path = root / "calls"
            fake_bin.mkdir()
            git = fake_bin / "git"
            git.write_text(
                textwrap.dedent(
                    f"""\
                    #!/bin/sh
                    printf '%s\\n' "$*" >> "{calls_path}"
                    if [ "$1" = "config" ] && [ "$2" = "--system" ] && [ "$3" = "--get-all" ] && [ "$4" = "safe.directory" ]; then
                        [ -f "{config_path}" ] && cat "{config_path}"
                        exit 0
                    fi
                    if [ "$1" = "config" ] && [ "$2" = "--system" ] && [ "$3" = "--add" ] && [ "$4" = "safe.directory" ]; then
                        printf '%s\\n' "$5" >> "{config_path}"
                        exit 0
                    fi
                    exit 1
                    """
                )
            )
            git.chmod(0o755)

            snippet = textwrap.dedent(
                f"""\
                set -e
                {self.installer_function("ensure_git_safe_directory")}
                export PATH="{fake_bin}:$PATH"
                ensure_git_safe_directory "/opt/SimpleSaferServer"
                ensure_git_safe_directory "/opt/SimpleSaferServer"
                """
            )

            result = subprocess.run(
                ["bash", "-lc", snippet],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            config_text = config_path.read_text()
            self.assertEqual(config_text.count("/opt/SimpleSaferServer"), 1)
            self.assertEqual(
                [line for line in calls_path.read_text().splitlines() if "--add" in line],
                ["config --system --add safe.directory /opt/SimpleSaferServer"],
            )

    def test_app_rsyncs_prune_removed_app_owned_files(self):
        text = INSTALL_SCRIPT.read_text()

        self.assertIn("rsync -a --delete", text)
        self.assertIn("--exclude='.venv'", text)
        self.assertNotIn("--exclude='venv'", text)
        self.assertIn("rsync -a --delete static", text)
        self.assertIn("rsync -a --delete templates", text)
        self.assertNotIn("rsync -a --delete harddrive_model/", text)
        self.assertNotIn("LEGACY_VENV_DIR", text)

    def test_core_dependency_install_does_not_include_optional_wsdd_daemons(self):
        text = INSTALL_SCRIPT.read_text()
        core_install_line = next(
            line for line in text.splitlines() if "apt-get install -y git ca-certificates" in line
        )

        self.assertIn("samba", core_install_line)
        self.assertNotIn("python3-flask", core_install_line)
        self.assertNotIn("python3-psutil", core_install_line)
        self.assertNotIn("python3-cryptography", core_install_line)
        self.assertNotIn("wsdd2", core_install_line)
        self.assertNotIn("wsdd", core_install_line)

    def test_optional_wsdd2_install_warns_and_continues(self):
        snippet = textwrap.dedent(
            f"""\
            set -e
            {self.installer_function("install_optional_wsdd2")}
            apt-get() {{
                printf '%s\\n' "$*" >> "$CALLS_PATH"
                return 42
            }}
            export CALLS_PATH="{Path(tempfile.gettempdir()) / "sss-wsdd2-install-calls"}"
            rm -f "$CALLS_PATH"
            install_optional_wsdd2
            cat "$CALLS_PATH"
            """
        )

        result = subprocess.run(
            ["bash", "-lc", snippet],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("install -y wsdd2", result.stdout)
        self.assertIn("Continuing without modern Windows discovery", result.stdout)

    def test_samba_layout_helper_invoked_without_creating_backup_share(self):
        text = INSTALL_SCRIPT.read_text()

        self.assertIn("SambaLayoutService(runtime=rt).ensure_layout()", text)
        self.assertNotIn("create_share('backup'", text)
        self.assertNotIn('create_share("backup"', text)

    def test_samba_services_fail_for_smbd_and_continue_for_discovery(self):
        snippet = textwrap.dedent(
            f"""\
            set -e
            {self.installer_function("configure_samba_discovery_services")}
            systemctl() {{
                printf '%s\\n' "$*" >> "$CALLS_PATH"
                if [ "$1" = "is-active" ] && [ "$2" = "--quiet" ] && [ "$3" = "smbd" ]; then
                    return 1
                fi
                return 0
            }}
            command() {{
                if [ "$1" = "-v" ] && [ "$2" = "systemctl" ]; then
                    return 0
                fi
                builtin command "$@"
            }}
            export CALLS_PATH="{Path(tempfile.gettempdir()) / "sss-samba-service-calls"}"
            rm -f "$CALLS_PATH"
            configure_samba_discovery_services
            """
        )

        result = subprocess.run(
            ["bash", "-lc", snippet],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERROR: smbd is not active", result.stdout)
        self.assertIn("systemctl status smbd", result.stdout)

    def test_top_level_installer_honors_samba_service_setup_failure(self):
        text = INSTALL_SCRIPT.read_text()
        samba_step = text[
            text.index("# 8. Prepare the SSS-owned Samba include layout") : text.index(
                "# 9. Install/refresh systemd service for Flask app"
            )
        ]

        self.assertIn("if configure_samba_discovery_services; then", samba_step)
        self.assertIn("ERROR: Failed to start required Samba file serving.", samba_step)
        self.assertIn("exit 1", samba_step)

    def test_samba_service_setup_warns_when_smbd_enable_fails_but_active(self):
        snippet = textwrap.dedent(
            f"""\
            set -e
            {self.installer_function("configure_samba_discovery_services")}
            systemctl() {{
                printf '%s\\n' "$*" >> "$CALLS_PATH"
                case "$*" in
                    "enable smbd") return 1 ;;
                    "is-active --quiet smbd") return 0 ;;
                    *) return 0 ;;
                esac
            }}
            command() {{
                if [ "$1" = "-v" ] && [ "$2" = "systemctl" ]; then
                    return 0
                fi
                builtin command "$@"
            }}
            export CALLS_PATH="{Path(tempfile.gettempdir()) / "sss-smbd-enable-warning-calls"}"
            rm -f "$CALLS_PATH"
            configure_samba_discovery_services
            cat "$CALLS_PATH"
            """
        )

        result = subprocess.run(
            ["bash", "-lc", snippet],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("WARNING: smbd is active, but systemctl enable smbd failed", result.stdout)
        self.assertIn("smbd: active", result.stdout)

    def test_samba_service_setup_warns_when_smbd_start_fails_but_active(self):
        snippet = textwrap.dedent(
            f"""\
            set -e
            {self.installer_function("configure_samba_discovery_services")}
            systemctl() {{
                printf '%s\\n' "$*" >> "$CALLS_PATH"
                case "$*" in
                    "restart smbd") return 1 ;;
                    "is-active --quiet smbd") return 0 ;;
                    *) return 0 ;;
                esac
            }}
            smbcontrol() {{
                return 1
            }}
            command() {{
                if [ "$1" = "-v" ] && [ "$2" = "systemctl" ]; then
                    return 0
                fi
                builtin command "$@"
            }}
            export CALLS_PATH="{Path(tempfile.gettempdir()) / "sss-smbd-start-warning-calls"}"
            rm -f "$CALLS_PATH"
            configure_samba_discovery_services
            cat "$CALLS_PATH"
            """
        )

        result = subprocess.run(
            ["bash", "-lc", snippet],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("WARNING: smbd is active, but reload/restart failed", result.stdout)
        self.assertIn("smbd: active", result.stdout)

    def test_samba_services_summary_reports_best_effort_discovery(self):
        snippet = textwrap.dedent(
            f"""\
            set -e
            {self.installer_function("configure_samba_discovery_services")}
            systemctl() {{
                printf '%s\\n' "$*" >> "$CALLS_PATH"
                case "$*" in
                    "is-active --quiet smbd") return 0 ;;
                    "is-active --quiet nmbd") return 1 ;;
                    "is-active --quiet wsdd2") return 1 ;;
                    *) return 0 ;;
                esac
            }}
            command() {{
                if [ "$1" = "-v" ] && [ "$2" = "systemctl" ]; then
                    return 0
                fi
                builtin command "$@"
            }}
            export CALLS_PATH="{Path(tempfile.gettempdir()) / "sss-samba-summary-calls"}"
            rm -f "$CALLS_PATH"
            configure_samba_discovery_services
            cat "$CALLS_PATH"
            """
        )

        result = subprocess.run(
            ["bash", "-lc", snippet],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("enable smbd", result.stdout)
        self.assertIn("start smbd", result.stdout)
        self.assertIn("enable nmbd", result.stdout)
        self.assertIn("start nmbd", result.stdout)
        self.assertIn("enable wsdd2", result.stdout)
        self.assertIn("start wsdd2", result.stdout)
        self.assertIn("smbd: active", result.stdout)
        self.assertIn("nmbd: inactive", result.stdout)
        self.assertIn("wsdd2: inactive", result.stdout)

    def test_samba_services_summary_reports_unavailable_when_unit_missing(self):
        snippet = textwrap.dedent(
            f"""\
            set -e
            {self.installer_function("configure_samba_discovery_services")}
            systemctl() {{
                printf '%s\\n' "$*" >> "$CALLS_PATH"
                case "$*" in
                    "is-active --quiet smbd") return 0 ;;
                    "is-active --quiet nmbd") return 0 ;;
                    "is-active --quiet wsdd2") return 1 ;;
                    "cat wsdd2") return 1 ;;
                    *) return 0 ;;
                esac
            }}
            command() {{
                if [ "$1" = "-v" ] && [ "$2" = "systemctl" ]; then
                    return 0
                fi
                builtin command "$@"
            }}
            export CALLS_PATH="{Path(tempfile.gettempdir()) / "sss-samba-unavailable-calls"}"
            rm -f "$CALLS_PATH"
            configure_samba_discovery_services
            cat "$CALLS_PATH"
            """
        )

        result = subprocess.run(
            ["bash", "-lc", snippet],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("smbd: active", result.stdout)
        self.assertIn("nmbd: active", result.stdout)
        self.assertIn("wsdd2: unavailable", result.stdout)


if __name__ == "__main__":
    unittest.main()
