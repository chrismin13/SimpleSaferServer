import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "install.sh"


class InstallPreflightTests(unittest.TestCase):
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

    def test_legacy_platform_warns_but_passes(self):
        result = self.run_preflight(
            """
            ID=debian
            VERSION_ID="10"
            PRETTY_NAME="Debian GNU/Linux 10 (buster)"
            """
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("legacy compatibility platform", result.stdout)

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


if __name__ == "__main__":
    unittest.main()
