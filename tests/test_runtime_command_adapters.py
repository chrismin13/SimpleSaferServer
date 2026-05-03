import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from simple_safer_server.adapters.command_runner import CommandRunner
from simple_safer_server.adapters.storage_commands import StorageCommandAdapter
from simple_safer_server.adapters.system_updates_commands import SystemUpdatesCommandAdapter
from simple_safer_server.adapters.user_commands import UserCommandAdapter


class RecordingRunner(CommandRunner):
    def __init__(self):
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")


class RuntimeCommandAdapterTests(unittest.TestCase):
    def test_storage_adapter_uses_root_direct_commands(self):
        runner = RecordingRunner()
        adapter = StorageCommandAdapter(command_runner=runner)

        adapter.reboot()
        adapter.poweroff()
        adapter.mount("/dev/sdb1", "/media/backup")
        adapter.start_unit("smbd")

        self.assertEqual(
            [call[0] for call in runner.calls],
            [
                ["systemctl", "reboot"],
                ["systemctl", "poweroff"],
                ["mount", "/dev/sdb1", "/media/backup"],
                ["systemctl", "start", "smbd"],
            ],
        )

    def test_user_adapter_uses_root_direct_commands(self):
        runner = RecordingRunner()
        adapter = UserCommandAdapter(command_runner=runner)

        adapter.create_system_user("operator")
        adapter.samba_users()
        adapter.set_samba_password("operator", "secret")
        adapter.remove_samba_user("operator")

        self.assertEqual(
            [call[0] for call in runner.calls],
            [
                ["useradd", "-m", "-s", "/bin/bash", "operator"],
                ["pdbedit", "-L"],
                ["smbpasswd", "-s", "-a", "operator"],
                ["smbpasswd", "-x", "operator"],
            ],
        )

    def test_system_updates_adapter_uses_root_direct_commands(self):
        runner = RecordingRunner()
        adapter = SystemUpdatesCommandAdapter(command_runner=runner)

        adapter.remove_files(["/var/lib/dpkg/lock"])
        adapter.pro_attach("/usr/bin/pro", Path("/tmp/attach-config.yaml"))
        adapter.pro_enable_livepatch("/usr/bin/pro")

        self.assertEqual(
            [call[0] for call in runner.calls],
            [
                ["rm", "-f", "/var/lib/dpkg/lock"],
                ["/usr/bin/pro", "attach", "--attach-config", "/tmp/attach-config.yaml"],
                ["/usr/bin/pro", "enable", "livepatch"],
            ],
        )

    def test_system_updates_adapter_skips_empty_remove_batch(self):
        runner = RecordingRunner()
        adapter = SystemUpdatesCommandAdapter(command_runner=runner)

        result = adapter.remove_files([])

        self.assertIsNone(result)
        self.assertEqual(runner.calls, [])

    def test_system_updates_adapter_writes_apt_periodic_config_directly(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "20auto-upgrades"
            adapter = SystemUpdatesCommandAdapter(apt_periodic_path=destination)
            source = Path(temp_dir) / "source"
            source.write_text('APT::Periodic::Update-Package-Lists "1";\n')

            with source.open("r") as temp_file:
                adapter.write_apt_periodic_config(temp_file)

            self.assertEqual(destination.read_text(), source.read_text())
            self.assertEqual(destination.stat().st_mode & 0o777, 0o644)


if __name__ == "__main__":
    unittest.main()
