import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from system_updates import (
    SystemUpdatesManager,
    get_support_info,
    parse_os_release_text,
)


def make_runtime(root: Path):
    return SimpleNamespace(
        mode="fake",
        is_fake=True,
        data_dir=root,
        config_dir=root / "config",
        default_mount_point=str(root / "backup"),
    )


class FakeConfigManager:
    def __init__(self):
        self.values = {}

    def get_value(self, section, key, default=None):
        return self.values.get((section, key), default)

    def set_value(self, section, key, value):
        self.values[(section, key)] = str(value)


class SystemUpdatesTests(unittest.TestCase):
    def test_parse_os_release_text_handles_quotes_and_comments(self):
        values = parse_os_release_text(
            """
            NAME="Ubuntu"
            VERSION_ID="24.04"
            # ignored
            ID=ubuntu
            """
        )

        self.assertEqual(values["ID"], "ubuntu")
        self.assertEqual(values["VERSION_ID"], "24.04")

    def test_debian_support_uses_major_version(self):
        support = get_support_info("debian", "12.7")

        self.assertTrue(support["known"])
        self.assertEqual(support["standard_eol"], "2026-06-10")
        self.assertEqual(support["max_eol"], "2028-06-30")

    def test_ubuntu_support_uses_major_minor_version(self):
        support = get_support_info("ubuntu", "24.04.4")

        self.assertTrue(support["known"])
        self.assertEqual(support["standard_eol_display"], "June 2029")
        self.assertEqual(support["max_eol_display"], "April 2034")

    def test_ubuntu_support_excludes_paid_legacy_add_on_dates(self):
        support = get_support_info("ubuntu", "22.04")

        self.assertTrue(support["known"])
        self.assertEqual(support["max_eol"], "2032-04-30")
        self.assertIn("excludes the paid Legacy", support["notes"])

    def test_remove_stale_locks_refuses_active_apt_processes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = make_runtime(Path(temp_dir))
            manager = SystemUpdatesManager(FakeConfigManager(), runtime=runtime)

            with patch.object(
                manager,
                "get_lock_status",
                return_value={
                    "locked": True,
                    "own_operation_running": False,
                    "held_locks": [],
                    "processes": [{"pid": 123, "name": "apt-get"}],
                },
            ):
                with self.assertRaises(RuntimeError):
                    manager.remove_stale_locks()

    def test_settings_are_saved_to_config_in_fake_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = make_runtime(Path(temp_dir))
            config = FakeConfigManager()
            manager = SystemUpdatesManager(config, runtime=runtime)

            settings = manager.save_settings({
                "update_package_lists": True,
                "unattended_upgrade": True,
                "autoclean": False,
            })

            self.assertTrue(settings["update_package_lists"])
            self.assertTrue(settings["unattended_upgrade"])
            self.assertFalse(settings["autoclean"])
            self.assertEqual(config.get_value("apt_updates", "update_package_lists"), "true")


if __name__ == "__main__":
    unittest.main()
