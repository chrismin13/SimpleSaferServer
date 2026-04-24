import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from system_updates import (
    DEFAULT_AUTOCLEAN_INTERVAL_DAYS,
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


def make_real_runtime(root: Path):
    return SimpleNamespace(
        mode="real",
        is_fake=False,
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

    def test_support_warns_when_eol_is_within_six_months(self):
        support = get_support_info("debian", "11", today=date(2026, 3, 1))

        self.assertTrue(support["is_supported"])
        self.assertTrue(support["approaching_eol"])
        self.assertEqual(support["days_until_eol"], 183)

    def test_support_does_not_warn_more_than_six_months_before_eol(self):
        support = get_support_info("debian", "11", today=date(2026, 2, 28))

        self.assertTrue(support["is_supported"])
        self.assertFalse(support["approaching_eol"])
        self.assertEqual(support["days_until_eol"], 184)

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

    def test_status_clears_stale_running_state_after_restart_when_apt_is_idle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = make_real_runtime(Path(temp_dir))
            manager = SystemUpdatesManager(FakeConfigManager(), runtime=runtime)
            manager._update_state(operation="update", status="running", phase="Downloading", progress=42)

            with patch.object(
                manager,
                "get_lock_status",
                return_value={
                    "locked": False,
                    "own_operation_running": False,
                    "held_locks": [],
                    "processes": [],
                },
            ):
                status = manager.get_status()

            self.assertEqual(status["status"], "failure")
            self.assertEqual(status["phase"], "Interrupted")
            self.assertIn("restarted", status["error"])
            self.assertIsNotNone(status["finished_at"])

    def test_status_marks_stale_running_state_external_when_apt_is_still_busy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = make_real_runtime(Path(temp_dir))
            manager = SystemUpdatesManager(FakeConfigManager(), runtime=runtime)
            manager._update_state(operation="upgrade", status="running", phase="Configuring", progress=74)

            lock_status = {
                "locked": True,
                "own_operation_running": False,
                "held_locks": ["/var/lib/dpkg/lock-frontend"],
                "processes": [{"pid": 123, "name": "apt-get", "cmdline": "apt-get upgrade"}],
            }
            with patch.object(manager, "get_lock_status", return_value=lock_status):
                status = manager.get_status()

            self.assertEqual(status["status"], "external")
            self.assertEqual(status["phase"], "Package manager busy")
            self.assertIn("still active", status["error"])
            self.assertEqual(status["lock"], lock_status)

    def test_status_keeps_running_state_for_current_worker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = make_real_runtime(Path(temp_dir))
            manager = SystemUpdatesManager(FakeConfigManager(), runtime=runtime)
            manager._update_state(operation="update", status="running", phase="Starting", progress=3)

            lock_status = {
                "locked": True,
                "own_operation_running": True,
                "held_locks": [],
                "processes": [],
            }
            with patch.object(manager, "get_lock_status", return_value=lock_status):
                status = manager.get_status()

            self.assertEqual(status["status"], "running")
            self.assertEqual(status["phase"], "Starting")
            self.assertEqual(status["lock"], lock_status)

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
            self.assertTrue(settings["apt_updates_managed"])
            self.assertEqual(settings["autoclean_interval"], 0)
            self.assertEqual(config.get_value("apt_updates", "managed"), "true")
            self.assertEqual(config.get_value("apt_updates", "update_package_lists"), "true")

    def test_unmanaged_settings_ignore_seeded_app_defaults_and_use_system_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = make_runtime(Path(temp_dir))
            config = FakeConfigManager()
            config.set_value("apt_updates", "managed", "false")
            config.set_value("apt_updates", "update_package_lists", "false")
            config.set_value("apt_updates", "unattended_upgrade", "false")
            config.set_value("apt_updates", "autoclean_interval", "7")
            manager = SystemUpdatesManager(config, runtime=runtime)

            with patch.object(
                manager,
                "_read_apt_periodic_config",
                return_value={
                    "update_package_lists": True,
                    "unattended_upgrade": True,
                    "autoclean_interval": 14,
                },
            ):
                settings = manager.get_settings()

            self.assertFalse(settings["apt_updates_managed"])
            self.assertTrue(settings["update_package_lists"])
            self.assertTrue(settings["unattended_upgrade"])
            self.assertTrue(settings["autoclean"])
            self.assertEqual(settings["autoclean_interval"], 14)

    def test_parse_apt_periodic_config_keeps_numeric_autoclean_interval(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = make_runtime(Path(temp_dir))
            manager = SystemUpdatesManager(FakeConfigManager(), runtime=runtime)

            values = manager._parse_apt_periodic_config(
                '''
                APT::Periodic::Update-Package-Lists "1";
                APT::Periodic::Unattended-Upgrade "0";
                APT::Periodic::AutocleanInterval "14";
                '''
            )

            self.assertTrue(values["update_package_lists"])
            self.assertFalse(values["unattended_upgrade"])
            self.assertEqual(values["autoclean_interval"], 14)

    def test_first_save_preserves_existing_positive_autoclean_interval(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = make_runtime(Path(temp_dir))
            config = FakeConfigManager()
            manager = SystemUpdatesManager(config, runtime=runtime)

            with patch.object(
                manager,
                "_read_apt_periodic_config",
                return_value={
                    "update_package_lists": True,
                    "unattended_upgrade": False,
                    "autoclean_interval": 14,
                },
            ):
                settings = manager.save_settings({
                    "update_package_lists": True,
                    "unattended_upgrade": False,
                    "autoclean": True,
                })

            self.assertTrue(settings["apt_updates_managed"])
            self.assertEqual(settings["autoclean_interval"], 14)
            self.assertEqual(config.get_value("apt_updates", "autoclean_interval"), "14")

    def test_enabling_autoclean_without_existing_interval_uses_default_interval(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = make_runtime(Path(temp_dir))
            config = FakeConfigManager()
            manager = SystemUpdatesManager(config, runtime=runtime)

            with patch.object(manager, "_read_apt_periodic_config", return_value={}):
                settings = manager.save_settings({
                    "update_package_lists": False,
                    "unattended_upgrade": False,
                    "autoclean": True,
                })

            self.assertEqual(settings["autoclean_interval"], DEFAULT_AUTOCLEAN_INTERVAL_DAYS)
            self.assertEqual(config.get_value("apt_updates", "autoclean_interval"), str(DEFAULT_AUTOCLEAN_INTERVAL_DAYS))

    def test_managed_config_overrides_system_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = make_runtime(Path(temp_dir))
            config = FakeConfigManager()
            config.set_value("apt_updates", "managed", "true")
            config.set_value("apt_updates", "update_package_lists", "false")
            config.set_value("apt_updates", "unattended_upgrade", "true")
            config.set_value("apt_updates", "autoclean_interval", "30")
            manager = SystemUpdatesManager(config, runtime=runtime)

            with patch.object(
                manager,
                "_read_apt_periodic_config",
                return_value={
                    "update_package_lists": True,
                    "unattended_upgrade": False,
                    "autoclean_interval": 14,
                },
            ):
                settings = manager.get_settings()

            self.assertTrue(settings["apt_updates_managed"])
            self.assertFalse(settings["update_package_lists"])
            self.assertTrue(settings["unattended_upgrade"])
            self.assertEqual(settings["autoclean_interval"], 30)

    def test_write_apt_periodic_config_emits_managed_comments_and_interval(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = make_runtime(Path(temp_dir))
            manager = SystemUpdatesManager(FakeConfigManager(), runtime=runtime)
            captured = {}

            def fake_run(args, **kwargs):
                captured["args"] = args
                captured["content"] = kwargs["stdin"].read()
                return SimpleNamespace(returncode=0)

            with patch("system_updates.subprocess.run", side_effect=fake_run):
                manager._write_apt_periodic_config({
                    "update_package_lists": True,
                    "unattended_upgrade": False,
                    "autoclean_interval": 14,
                })

        self.assertEqual(captured["args"], ["sudo", "tee", "/etc/apt/apt.conf.d/20auto-upgrades"])
        self.assertIn("// Managed by SimpleSaferServer.", captured["content"])
        self.assertIn('APT::Periodic::Update-Package-Lists "1";', captured["content"])
        self.assertIn('APT::Periodic::Unattended-Upgrade "0";', captured["content"])
        self.assertIn('APT::Periodic::AutocleanInterval "14";', captured["content"])

    def test_failed_real_write_does_not_claim_apt_update_ownership(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = make_real_runtime(root)
            config = FakeConfigManager()
            manager = SystemUpdatesManager(config, runtime=runtime)

            with patch.object(manager, "_read_apt_periodic_config", return_value={}):
                with patch.object(manager, "_write_apt_periodic_config", side_effect=RuntimeError("write failed")):
                    with self.assertRaisesRegex(RuntimeError, "write failed"):
                        manager.save_settings({
                            "update_package_lists": True,
                            "unattended_upgrade": True,
                            "autoclean": True,
                        })

            self.assertIsNone(config.get_value("apt_updates", "managed", None))

    def test_livepatch_setup_uses_pro_attach_config_without_token_in_argv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manager = SystemUpdatesManager(FakeConfigManager(), runtime=make_real_runtime(root))
            calls = []
            seen_attach_config = {}

            def fake_run(args, **kwargs):
                calls.append(args)
                self.assertNotIn("secret-token", args)
                if args[:3] == ["sudo", "/usr/bin/pro", "attach"]:
                    attach_config = Path(args[-1])
                    seen_attach_config["path"] = attach_config
                    seen_attach_config["content"] = attach_config.read_text()
                return SimpleNamespace(returncode=0, stdout="", stderr="", args=args)

            with patch.object(manager, "get_distribution_info", return_value={"id": "ubuntu"}):
                with patch.object(manager, "get_livepatch_status", return_value={"enabled": True}) as status:
                    with patch("system_updates.shutil.which", return_value="/usr/bin/pro"):
                        with patch("system_updates.subprocess.run", side_effect=fake_run):
                            result = manager.setup_livepatch("secret-token")

            self.assertEqual(result, {"enabled": True})
            self.assertEqual(calls[0][:4], ["sudo", "/usr/bin/pro", "attach", "--attach-config"])
            self.assertEqual(calls[1], ["sudo", "/usr/bin/pro", "enable", "livepatch"])
            self.assertIn('token: "secret-token"', seen_attach_config["content"])
            self.assertFalse(seen_attach_config["path"].exists())
            status.assert_called_once()

    def test_livepatch_setup_enables_livepatch_when_machine_is_already_attached(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = SystemUpdatesManager(FakeConfigManager(), runtime=make_real_runtime(Path(temp_dir)))
            calls = []

            def fake_run(args, **kwargs):
                calls.append(args)
                if args[:3] == ["sudo", "/usr/bin/pro", "attach"]:
                    return SimpleNamespace(returncode=2, stdout="", stderr="already attached", args=args)
                return SimpleNamespace(returncode=0, stdout="", stderr="", args=args)

            with patch.object(manager, "get_distribution_info", return_value={"id": "ubuntu"}):
                with patch.object(manager, "get_livepatch_status", return_value={"enabled": True}):
                    with patch("system_updates.shutil.which", return_value="/usr/bin/pro"):
                        with patch("system_updates.subprocess.run", side_effect=fake_run):
                            manager.setup_livepatch("secret-token")

            self.assertEqual(calls[-1], ["sudo", "/usr/bin/pro", "enable", "livepatch"])

    def test_livepatch_setup_requires_ubuntu_pro_client(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = SystemUpdatesManager(FakeConfigManager(), runtime=make_real_runtime(Path(temp_dir)))

            with patch.object(manager, "get_distribution_info", return_value={"id": "ubuntu"}):
                with patch("system_updates.shutil.which", return_value=None):
                    with self.assertRaisesRegex(RuntimeError, "Ubuntu Pro Client is required"):
                        manager.setup_livepatch("secret-token")


if __name__ == "__main__":
    unittest.main()
