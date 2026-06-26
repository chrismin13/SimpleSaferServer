import os
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "install.sh"
INDEX_HTML = REPO_ROOT / "index.html"
WEB_SERVICE_FILE = REPO_ROOT / "simple-safer-server-web.service"
WORKER_SERVICE_FILE = REPO_ROOT / "simple-safer-server-worker.service"


class InstallPreflightTests(unittest.TestCase):
    def installer_function(self, name):
        text = INSTALL_SCRIPT.read_text()
        start = text.index(f"{name}() {{")
        end = text.index("\n}\n\n", start) + len("\n}\n")
        return text[start:end]

    def run_preflight(self, os_release_text, *args, fake_commands="curl,systemctl,sudo"):
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

    def run_preflight_with_arch(self, os_release_text, arch):
        with tempfile.TemporaryDirectory() as temp_dir:
            os_release_path = Path(temp_dir) / "os-release"
            os_release_path.write_text(textwrap.dedent(os_release_text))
            env = {
                **os.environ,
                "SSS_INSTALLER_PREFLIGHT_ONLY": "1",
                "SSS_INSTALLER_TEST_COMMANDS": "curl,systemctl,sudo",
                "SSS_INSTALLER_TEST_SYSTEMD": "1",
                "SSS_INSTALLER_TEST_ARCH": arch,
                "SSS_OS_RELEASE_PATH": str(os_release_path),
            }
            return subprocess.run(
                ["bash", str(INSTALL_SCRIPT)],
                cwd=str(REPO_ROOT),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

    def test_unsupported_architectures_are_rejected(self):
        result = self.run_preflight(
            """
            ID=debian
            VERSION_ID="13"
            PRETTY_NAME="Debian GNU/Linux 13 (trixie)"
            """,
            fake_commands="curl,systemctl,sudo",
        )
        # The default test host architecture should pass; this keeps the arch
        # override test below focused on the unsupported userspace.
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

        for arch in ("armhf", "i386"):
            with self.subTest(arch=arch):
                arch_result = self.run_preflight_with_arch(
                    """
                    ID=debian
                    VERSION_ID="13"
                    PRETTY_NAME="Debian GNU/Linux 13 (trixie)"
                    """,
                    arch,
                )
                self.assertNotEqual(arch_result.returncode, 0)
                self.assertIn(
                    f"Unsupported architecture detected: {arch}",
                    arch_result.stdout,
                )

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
            fake_commands="curl",
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
                "SSS_INSTALLER_TEST_COMMANDS": "curl,systemctl,sudo",
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

    def test_missing_sudo_blocks(self):
        result = self.run_preflight(
            """
            ID=debian
            VERSION_ID="13"
            PRETTY_NAME="Debian GNU/Linux 13 (trixie)"
            """,
            fake_commands="curl,systemctl",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing required host tools", result.stdout)
        self.assertIn("sudo", result.stdout)

    def test_installer_declares_non_root_web_service_setup(self):
        script = INSTALL_SCRIPT.read_text()

        self.assertIn('APP_USER="sss"', script)
        self.assertIn('APP_GROUP="sss"', script)
        self.assertIn('SERVICE_USER_MARKER="$DATA_DIR/.sss-user-created"', script)
        self.assertIn('SERVICE_GROUP_MARKER="$DATA_DIR/.sss-group-created"', script)
        self.assertIn('useradd \\', script)
        self.assertIn('printf \'%s ALL=(root) NOPASSWD: %s/sss-helper\\n\'', script)
        self.assertIn('sudo -u "$APP_USER" -n "$VENV_DIR/bin/python3"', script)

    def test_web_service_runs_as_service_user(self):
        service = WEB_SERVICE_FILE.read_text()

        self.assertIn("User=sss", service)
        self.assertIn("Group=sss", service)
        self.assertIn("RuntimeDirectory=SimpleSaferServer", service)
        self.assertNotIn("User=root", service)

    def test_worker_service_runs_as_service_user(self):
        service = WORKER_SERVICE_FILE.read_text()

        self.assertIn("User=sss", service)
        self.assertIn("Group=sss", service)
        self.assertIn("RuntimeDirectory=SimpleSaferServer", service)
        self.assertNotIn("User=root", service)

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

    def test_installer_excludes_dev_scripts_from_production_app_copy(self):
        text = INSTALL_SCRIPT.read_text()

        self.assertIn('--exclude="./scripts"', text)
        self.assertNotIn("for script in scripts/*.sh scripts/*.py", text)
        self.assertNotIn("chmod +x \"$app_script_path\"", text)

    def test_app_tar_copy_prunes_removed_app_owned_files(self):
        text = INSTALL_SCRIPT.read_text()

        self.assertIn('find "$APP_DIR" -mindepth 1 -maxdepth 1 ! -name ".venv"', text)
        self.assertIn('tar \\', text)
        self.assertIn('--exclude="./.git"', text)
        self.assertIn('--exclude="./.venv"', text)
        self.assertNotIn("--exclude='venv'", text)
        self.assertNotIn("rsync -a --delete", text)

    def test_base_installer_does_not_install_apt_packages(self):
        text = INSTALL_SCRIPT.read_text()
        active_script = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("#")
        )

        self.assertNotIn("apt-get install", text)
        self.assertNotIn("apt-get update", text)
        self.assertNotIn("apt install", text)
        self.assertNotIn("DEBIAN_FRONTEND=noninteractive", text)
        self.assertNotRegex(
            active_script,
            re.compile(r"\b(?:apt|apt-get|aptitude)\b[^\n]*\b(?:install|update|upgrade)\b"),
        )
        self.assertNotRegex(
            active_script,
            re.compile(r"\bdpkg\b[^\n]*\b(?:--install|-i)\b"),
        )
        for package in (
            "samba",
            "wsdd2",
            "rclone",
            "smartmontools",
            "hdsentinel",
            "ntfs-3g",
            "unattended-upgrades",
            "msmtp",
            "git",
            "ca-certificates",
        ):
            self.assertNotIn(f"install {package}", text)
            self.assertNotIn(f"install -y {package}", text)
            self.assertNotRegex(
                active_script,
                re.compile(
                    rf"\b(?:apt|apt-get|aptitude)\b[^\n]*\binstall\b[^\n]*\b{re.escape(package)}\b"
                ),
            )
        self.assertNotIn(
            'install -d -o "$APP_USER" -g "$APP_GROUP" -m 0750 "$CONFIG_DIR/rclone"',
            text,
        )

    def test_public_install_page_matches_base_install_boundary(self):
        page = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("static/vendor/fontawesome/6.4.0/css/all.min.css", page)
        self.assertIn("web and worker services", page)
        self.assertIn("belong to module setup flows instead of the base install", page)
        self.assertNotIn("cdn.jsdelivr.net", page)
        self.assertNotIn("cdnjs.cloudflare.com", page)
        self.assertNotIn("fonts.googleapis.com", page)
        self.assertNotIn("fonts.gstatic.com", page)
        self.assertNotIn("before installing packages", page)
        self.assertNotIn("services, timers", page)

    def test_base_installer_does_not_prepare_samba(self):
        text = INSTALL_SCRIPT.read_text()

        self.assertNotIn("SambaLayoutService(runtime=rt).ensure_layout()", text)
        self.assertNotIn("configure_samba_discovery_services", text)
        self.assertNotIn("systemctl enable smbd", text)
        self.assertNotIn("systemctl start smbd", text)
        self.assertNotIn("create_share('backup'", text)
        self.assertNotIn('create_share("backup"', text)

    def test_base_installer_does_not_change_firewall_policy(self):
        text = INSTALL_SCRIPT.read_text()

        self.assertNotIn("ufw allow", text)
        self.assertNotIn("firewall-cmd", text)
        self.assertNotIn("iptables -A", text)
        self.assertNotIn("iptables -C", text)

    def test_installer_declares_worker_service_and_sss_cli_wrapper(self):
        text = INSTALL_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("simple-safer-server-worker.service", text)
        self.assertIn("simple_safer_server.cli", text)
        self.assertIn("simple_safer_server.privileged_helper", text)
        self.assertIn('cat >"$BIN_DIR/sss"', text)
        self.assertIn('cat >"$BIN_DIR/sss-helper"', text)
        self.assertNotIn('bin_script_path="$BIN_DIR/$script_name"', text)


if __name__ == "__main__":
    unittest.main()
