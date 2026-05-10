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
                {self.installer_function("copy_unless_same_file")}
                SCRIPTS_DIR="{scripts_dir}"
                BIN_DIR="{bin_dir}"
                cd "{root}"
                for script in scripts/*.sh scripts/*.py; do
                  script_name="$(basename "$script")"
                  app_script_path="$SCRIPTS_DIR/$script_name"
                  bin_script_path="$BIN_DIR/$script_name"
                  copy_unless_same_file "$script" "$app_script_path"
                  chmod +x "$app_script_path"
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
            self.assertTrue(os.access(script, os.X_OK))
            self.assertTrue(os.access(py_script, os.X_OK))
            self.assertEqual((bin_dir / "app_update.sh").read_text(), "#!/bin/bash\necho app\n")

    def test_model_install_loop_skips_same_app_destination(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_dir = root / "harddrive_model"
            model_dir.mkdir()
            model = model_dir / "xgb_model.json"
            model.write_text('{"model": true}\n')

            snippet = textwrap.dedent(
                f"""\
                set -e
                {self.installer_function("copy_unless_same_file")}
                MODEL_DIR="{model_dir}"
                cd "{root}"
                for model_file in harddrive_model/*; do
                  model_name="$(basename "$model_file")"
                  model_dest_path="$MODEL_DIR/$model_name"
                  copy_unless_same_file "$model_file" "$model_dest_path"
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
            self.assertEqual(model.read_text(), '{"model": true}\n')


if __name__ == "__main__":
    unittest.main()
