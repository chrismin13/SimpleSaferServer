import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

from simple_safer_server.services.storage_service import StorageService


class FakeConfigManager:
    def __init__(self, mount_point, uuid: Optional[str] = "drive-uuid"):
        self.mount_point = mount_point
        self.uuid = uuid

    def get_value(self, section, key, default=None):
        values = {
            ("backup", "mount_point"): self.mount_point,
            ("backup", "uuid"): self.uuid,
        }
        return values.get((section, key), default)


class FakeState:
    def __init__(self):
        self.mounted = False
        self.logs = []

    def set_mount(self, mounted, mount_point=None):
        self.mounted = mounted

    def append_task_log(self, task_name, message):
        self.logs.append((task_name, message))


class FakeStorageCommandAdapter:
    def __init__(self):
        self.rebooted = False
        self.powered_off = False
        self.device = "/dev/sdb1"
        self.mounted = []
        self.started = []
        self.raise_on_mount = None  # type: Optional[Exception]

    def reboot(self):
        self.rebooted = True

    def poweroff(self):
        self.powered_off = True

    def find_device_by_uuid(self, uuid):
        return self.device

    def mount(self, device, mount_point):
        if self.raise_on_mount:
            raise self.raise_on_mount
        self.mounted.append((device, mount_point))

    def start_unit(self, unit_name):
        self.started.append(unit_name)


class StorageServiceTests(unittest.TestCase):
    def build_service(
        self,
        *,
        is_fake=False,
        mount_point=None,
        uuid: Optional[str] = "drive-uuid",
    ):
        runtime = SimpleNamespace(
            is_fake=is_fake,
            default_mount_point=mount_point or "/mnt/backups",
            repo_root=Path("."),
        )
        fake_state = FakeState()
        adapter = FakeStorageCommandAdapter()
        service = StorageService(
            runtime=runtime,
            fake_state=fake_state,
            config_manager=FakeConfigManager(runtime.default_mount_point, uuid=uuid),
            command_adapter=adapter,
        )
        return service, fake_state, adapter

    def test_restart_and_shutdown_delegate_to_command_adapter(self):
        service, _fake_state, adapter = self.build_service()

        self.assertEqual(
            service.restart_system(),
            ({"success": True, "message": "System is restarting..."}, 200),
        )
        self.assertEqual(
            service.shutdown_system(),
            ({"success": True, "message": "System is shutting down..."}, 200),
        )
        self.assertTrue(adapter.rebooted)
        self.assertTrue(adapter.powered_off)

    def test_fake_mount_sets_fake_state_without_system_commands(self):
        with tempfile.TemporaryDirectory() as mount_point:
            service, fake_state, adapter = self.build_service(is_fake=True, mount_point=mount_point)

            self.assertEqual(
                service.mount_dashboard_drive(),
                ({"success": True, "message": "Local backup source connected."}, 200),
            )
            self.assertTrue(fake_state.mounted)
            self.assertEqual(adapter.mounted, [])

    def test_real_mount_starts_related_services(self):
        with tempfile.TemporaryDirectory() as mount_point:
            service, _fake_state, adapter = self.build_service(mount_point=mount_point)

            self.assertEqual(
                service.mount_dashboard_drive(),
                ({"success": True, "message": "Drive mounted and available for use."}, 200),
            )
            self.assertEqual(adapter.mounted, [("/dev/sdb1", mount_point)])
        self.assertEqual(
            adapter.started,
            [
                "check_mount.service",
                "check_health.service",
                "backup_cloud.service",
                "smbd",
                "nmbd",
            ],
        )

    def test_real_mount_reports_missing_uuid_without_system_commands(self):
        service, _fake_state, adapter = self.build_service(uuid=None)

        self.assertEqual(
            service.mount_dashboard_drive(),
            ({"success": False, "message": "No drive UUID configured."}, 400),
        )
        self.assertEqual(adapter.mounted, [])

    def test_real_mount_preserves_called_process_error_message(self):
        with tempfile.TemporaryDirectory() as mount_point:
            service, _fake_state, adapter = self.build_service(mount_point=mount_point)
            adapter.raise_on_mount = subprocess.CalledProcessError(1, ["mount"])

            payload, status_code = service.mount_dashboard_drive()

        self.assertFalse(payload["success"])
        self.assertIn("Failed to mount drive:", payload["message"])
        self.assertEqual(status_code, 500)
