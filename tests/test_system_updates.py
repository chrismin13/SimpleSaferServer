import tempfile
import unittest
from pathlib import Path
from subprocess import CalledProcessError, TimeoutExpired
from types import SimpleNamespace
from unittest.mock import patch

from simple_safer_server.services.system_updates import (
    DEFAULT_AUTOCLEAN_INTERVAL_DAYS,
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
        self.apt_periodic_content = ""
        self.attach_returncode = 0

    def write_apt_periodic_config(self, temp_file):
        self.calls.append(("write_apt_periodic_config",))
        self.apt_periodic_content = temp_file.read()
        return SimpleNamespace(returncode=0)

    def pro_attach(self, pro_binary, attach_config_path):
        self.calls.append(("pro_attach", pro_binary, str(attach_config_path)))
        return SimpleNamespace(
            returncode=self.attach_returncode,
            stdout="",
            stderr="already attached" if self.attach_returncode == 2 else "",
            args=[pro_binary, "attach", "--attach-config", str(attach_config_path)],
        )

    def pro_enable_livepatch(self, pro_binary):
        self.calls.append(("pro_enable_livepatch", pro_binary))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def livepatch_status_json(self, binary):
        self.calls.append(("livepatch_status_json", binary))
        return SimpleNamespace(returncode=0, stdout='{"status": []}', stderr="")

    def livepatch_status_text(self, binary):
        self.calls.append(("livepatch_status_text", binary))
        return SimpleNamespace(returncode=0, stdout="enabled", stderr="")


class SystemUpdatesTests(unittest.TestCase):
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
            ), self.assertRaises(RuntimeError):
                manager.remove_stale_locks()

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

            with patch.object(
                manager, "get_distribution_info", return_value={"id": "ubuntu"}
            ), patch(
                "simple_safer_server.services.system_updates.shutil.which",
                return_value="/usr/bin/canonical-livepatch",
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

            with patch.object(
                manager, "get_distribution_info", return_value={"id": "ubuntu"}
            ), patch(
                "simple_safer_server.services.system_updates.shutil.which",
                return_value="/usr/bin/canonical-livepatch",
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

    def test_settings_are_saved_to_config_in_fake_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = make_runtime(Path(temp_dir))
            config = FakeConfigManager()
            manager = SystemUpdatesManager(config, runtime=runtime)

            settings = manager.save_settings(
                {
                    "update_package_lists": True,
                    "unattended_upgrade": True,
                    "autoclean": False,
                }
            )

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
                settings = manager.save_settings(
                    {
                        "update_package_lists": True,
                        "unattended_upgrade": False,
                        "autoclean": True,
                    }
                )

            self.assertTrue(settings["apt_updates_managed"])
            self.assertEqual(settings["autoclean_interval"], 14)
            self.assertEqual(config.get_value("apt_updates", "autoclean_interval"), "14")

    def test_enabling_autoclean_without_existing_interval_uses_default_interval(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = make_runtime(Path(temp_dir))
            config = FakeConfigManager()
            manager = SystemUpdatesManager(config, runtime=runtime)

            with patch.object(manager, "_read_apt_periodic_config", return_value={}):
                settings = manager.save_settings(
                    {
                        "update_package_lists": False,
                        "unattended_upgrade": False,
                        "autoclean": True,
                    }
                )

            self.assertEqual(settings["autoclean_interval"], DEFAULT_AUTOCLEAN_INTERVAL_DAYS)
            self.assertEqual(
                config.get_value("apt_updates", "autoclean_interval"),
                str(DEFAULT_AUTOCLEAN_INTERVAL_DAYS),
            )

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
            command_adapter = FakeSystemUpdatesCommandAdapter()
            manager = SystemUpdatesManager(
                FakeConfigManager(), runtime=runtime, command_adapter=command_adapter
            )

            manager._write_apt_periodic_config(
                {
                    "update_package_lists": True,
                    "unattended_upgrade": False,
                    "autoclean_interval": 14,
                }
            )

        self.assertEqual(command_adapter.calls, [("write_apt_periodic_config",)])
        self.assertFalse((runtime.data_dir / "20auto-upgrades").exists())
        self.assertIn("// Managed by SimpleSaferServer.", command_adapter.apt_periodic_content)
        self.assertIn(
            'APT::Periodic::Update-Package-Lists "1";', command_adapter.apt_periodic_content
        )
        self.assertIn(
            'APT::Periodic::Unattended-Upgrade "0";', command_adapter.apt_periodic_content
        )
        self.assertIn(
            'APT::Periodic::AutocleanInterval "14";', command_adapter.apt_periodic_content
        )

    def test_failed_real_write_does_not_claim_apt_update_ownership(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = make_real_runtime(root)
            config = FakeConfigManager()
            manager = SystemUpdatesManager(config, runtime=runtime)

            with patch.object(manager, "_read_apt_periodic_config", return_value={}):
                with patch.object(
                    manager, "_write_apt_periodic_config", side_effect=RuntimeError("write failed")
                ):
                    with self.assertRaisesRegex(RuntimeError, "write failed"):
                        manager.save_settings(
                            {
                                "update_package_lists": True,
                                "unattended_upgrade": True,
                                "autoclean": True,
                            }
                        )

            self.assertIsNone(config.get_value("apt_updates", "managed", None))

    def test_livepatch_setup_uses_pro_attach_config_without_token_in_argv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            command_adapter = FakeSystemUpdatesCommandAdapter()
            config = FakeConfigManager()
            manager = SystemUpdatesManager(
                config,
                runtime=make_real_runtime(root),
                command_adapter=command_adapter,
            )
            seen_attach_config = {}
            original_pro_attach = command_adapter.pro_attach

            def record_attach_config(pro_binary, attach_config_path):
                self.assertNotIn("secret-token", [pro_binary, str(attach_config_path)])
                seen_attach_config["path"] = attach_config_path
                seen_attach_config["content"] = attach_config_path.read_text()
                return original_pro_attach(pro_binary, attach_config_path)

            command_adapter.pro_attach = record_attach_config

            with patch.object(manager, "get_distribution_info", return_value={"id": "ubuntu"}):
                with patch.object(
                    manager, "get_livepatch_status", return_value={"enabled": True}
                ) as status:
                    with patch(
                        "simple_safer_server.services.system_updates.shutil.which",
                        return_value="/usr/bin/pro",
                    ):
                        result = manager.setup_livepatch("secret-token")

            self.assertEqual(result, {"enabled": True})
            self.assertEqual(command_adapter.calls[0][0], "pro_attach")
            self.assertEqual(command_adapter.calls[1], ("pro_enable_livepatch", "/usr/bin/pro"))
            self.assertIn('token: "secret-token"', seen_attach_config["content"])
            self.assertEqual(seen_attach_config["path"].parent, root / "run")
            self.assertFalse(seen_attach_config["path"].exists())
            self.assertEqual(config.get_value("system_updates", "livepatch_managed"), "true")
            status.assert_called_once()

    def test_livepatch_setup_enables_livepatch_when_machine_is_already_attached(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            command_adapter = FakeSystemUpdatesCommandAdapter()
            command_adapter.attach_returncode = 2
            manager = SystemUpdatesManager(
                FakeConfigManager(),
                runtime=make_real_runtime(Path(temp_dir)),
                command_adapter=command_adapter,
            )

            with patch.object(manager, "get_distribution_info", return_value={"id": "ubuntu"}):
                with patch.object(manager, "get_livepatch_status", return_value={"enabled": True}):
                    with patch(
                        "simple_safer_server.services.system_updates.shutil.which",
                        return_value="/usr/bin/pro",
                    ):
                        manager.setup_livepatch("secret-token")

            self.assertEqual(command_adapter.calls[-1], ("pro_enable_livepatch", "/usr/bin/pro"))

    def test_livepatch_setup_does_not_mark_fake_mode_as_managed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = FakeConfigManager()
            manager = SystemUpdatesManager(config, runtime=make_runtime(Path(temp_dir)))

            with patch.object(manager, "get_distribution_info", return_value={"id": "ubuntu"}):
                manager.setup_livepatch("secret-token")

            self.assertIsNone(config.get_value("system_updates", "livepatch_managed", None))

    def test_failed_livepatch_setup_does_not_claim_ownership(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            command_adapter = FakeSystemUpdatesCommandAdapter()
            command_adapter.attach_returncode = 1
            config = FakeConfigManager()
            manager = SystemUpdatesManager(
                config,
                runtime=make_real_runtime(Path(temp_dir)),
                command_adapter=command_adapter,
            )

            with patch.object(manager, "get_distribution_info", return_value={"id": "ubuntu"}):
                with patch(
                    "simple_safer_server.services.system_updates.shutil.which",
                    return_value="/usr/bin/pro",
                ):
                    with self.assertRaises(CalledProcessError):
                        manager.setup_livepatch("secret-token")

            self.assertIsNone(config.get_value("system_updates", "livepatch_managed", None))

    def test_livepatch_setup_requires_ubuntu_pro_client(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = SystemUpdatesManager(
                FakeConfigManager(), runtime=make_real_runtime(Path(temp_dir))
            )

            with patch.object(manager, "get_distribution_info", return_value={"id": "ubuntu"}):
                with patch(
                    "simple_safer_server.services.system_updates.shutil.which", return_value=None
                ):
                    with self.assertRaisesRegex(RuntimeError, "Ubuntu Pro Client is required"):
                        manager.setup_livepatch("secret-token")


if __name__ == "__main__":
    unittest.main()
