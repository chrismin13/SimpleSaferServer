import tempfile
import unittest
from pathlib import Path
from subprocess import TimeoutExpired
from types import SimpleNamespace
from unittest.mock import patch

from simple_safer_server.modules.system_updates.service import (
    SystemUpdatesManager,
    _is_apt_process,
)


def make_runtime(root: Path):
    return SimpleNamespace(
        mode="fake",
        is_fake=True,
        repo_root=root,
        data_dir=root,
        volatile_dir=root / "run",
        config_dir=root / "config",
        default_mount_point=str(root / "backup"),
    )


def make_real_runtime(root: Path):
    return SimpleNamespace(
        mode="real",
        is_fake=False,
        repo_root=root / "app",
        data_dir=root,
        volatile_dir=root / "run",
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


class FakeSystemUpdatesCommandAdapter:
    def __init__(self):
        self.calls = []

    def livepatch_status_json(self, binary):
        self.calls.append(("livepatch_status_json", binary))
        return SimpleNamespace(returncode=0, stdout='{"status": []}', stderr="")

    def livepatch_status_text(self, binary):
        self.calls.append(("livepatch_status_text", binary))
        return SimpleNamespace(returncode=0, stdout="enabled", stderr="")


class SystemUpdatesTests(unittest.TestCase):
    def test_apt_process_matching_uses_executable_tokens(self):
        self.assertTrue(_is_apt_process("apt-get", ["apt-get", "update"]))
        self.assertTrue(
            _is_apt_process(
                "env",
                ["env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "-y", "upgrade"],
            )
        )
        self.assertTrue(_is_apt_process("sudo", ["sudo", "apt-get", "update"]))
        self.assertTrue(
            _is_apt_process(
                "sudo",
                ["sudo", "env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "-y", "upgrade"],
            )
        )
        self.assertTrue(_is_apt_process("dpkg", ["/usr/bin/dpkg", "--configure", "-a"]))
        self.assertTrue(_is_apt_process("unattended-upgrade", ["/usr/bin/unattended-upgrade"]))

        self.assertFalse(_is_apt_process("adapt", ["/tmp/adapt", "--scan"]))
        self.assertFalse(_is_apt_process("python3", ["/srv/capture/report.py", "apt"]))
        self.assertFalse(
            _is_apt_process("backup", ["/usr/local/bin/backup", "/var/log/apt/history.log"])
        )

    def test_livepatch_json_status_timeout_returns_unavailable_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = make_real_runtime(Path(temp_dir))
            adapter = FakeSystemUpdatesCommandAdapter()
            adapter.livepatch_status_json = lambda binary: (_ for _ in ()).throw(
                TimeoutExpired(cmd=[binary, "status"], timeout=60)
            )
            manager = SystemUpdatesManager(
                FakeConfigManager(), runtime=runtime, command_adapter=adapter
            )

            with (
                patch.object(manager, "get_distribution_info", return_value={"id": "ubuntu"}),
                patch(
                    "simple_safer_server.modules.system_updates.service.shutil.which",
                    return_value="/usr/bin/canonical-livepatch",
                ),
            ):
                status = manager.get_livepatch_status()

        self.assertTrue(status["supported_distro"])
        self.assertFalse(status["installed"])
        self.assertFalse(status["enabled"])
        self.assertEqual(status["details"], {})
        self.assertIn("Livepatch status unavailable:", status["status_text"])

    def test_livepatch_text_status_os_error_returns_unavailable_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = make_real_runtime(Path(temp_dir))
            adapter = FakeSystemUpdatesCommandAdapter()
            adapter.livepatch_status_json = lambda binary: SimpleNamespace(
                returncode=1, stdout="", stderr="json failed"
            )
            adapter.livepatch_status_text = lambda binary: (_ for _ in ()).throw(
                OSError("cannot execute")
            )
            manager = SystemUpdatesManager(
                FakeConfigManager(), runtime=runtime, command_adapter=adapter
            )

            with (
                patch.object(manager, "get_distribution_info", return_value={"id": "ubuntu"}),
                patch(
                    "simple_safer_server.modules.system_updates.service.shutil.which",
                    return_value="/usr/bin/canonical-livepatch",
                ),
            ):
                status = manager.get_livepatch_status()

        self.assertTrue(status["supported_distro"])
        self.assertFalse(status["installed"])
        self.assertFalse(status["enabled"])
        self.assertEqual(status["details"], {})
        self.assertIn("cannot execute", status["status_text"])

    def test_status_clears_stale_running_state_after_restart_when_apt_is_idle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = make_real_runtime(Path(temp_dir))
            manager = SystemUpdatesManager(FakeConfigManager(), runtime=runtime)
            manager._update_state(
                operation="update", status="running", phase="Downloading", progress=42
            )

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
            manager._update_state(
                operation="upgrade", status="running", phase="Configuring", progress=74
            )

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
            manager._update_state(
                operation="update", status="running", phase="Starting", progress=3
            )

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

    def test_write_state_replaces_complete_json_atomically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = make_real_runtime(Path(temp_dir))
            manager = SystemUpdatesManager(FakeConfigManager(), runtime=runtime)

            manager._write_state({"status": "running", "phase": "Downloading"})

            state = manager._read_state()
            self.assertEqual(state["status"], "running")
            self.assertEqual(state["phase"], "Downloading")
            self.assertFalse(
                list(manager.state_path.parent.glob(f".{manager.state_path.name}.tmp.*"))
            )
            self.assertEqual(manager.state_path.stat().st_mode & 0o777, 0o644)

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
            self.assertTrue(settings["read_only"])
            self.assertNotIn("unattended_upgrades_installed", settings)

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

    def test_saved_app_apt_config_never_overrides_system_values(self):
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

            self.assertFalse(settings["apt_updates_managed"])
            self.assertTrue(settings["update_package_lists"])
            self.assertFalse(settings["unattended_upgrade"])
            self.assertEqual(settings["autoclean_interval"], 14)
            self.assertTrue(settings["read_only"])


if __name__ == "__main__":
    unittest.main()
