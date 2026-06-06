import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from unittest.mock import patch

from simple_safer_server.services.storage_service import StorageService
from simple_safer_server.web.problems import OperationProblem, ValidationProblem


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
        self.managed_mounted = []
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

    def mount_managed(self, mount_point):
        if self.raise_on_mount:
            raise self.raise_on_mount
        self.managed_mounted.append(mount_point)

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

        self.assertEqual(service.restart_system(), "System is restarting...")
        self.assertEqual(service.shutdown_system(), "System is shutting down...")
        self.assertTrue(adapter.rebooted)
        self.assertTrue(adapter.powered_off)

    def test_fake_mount_sets_fake_state_without_system_commands(self):
        with tempfile.TemporaryDirectory() as mount_point:
            service, fake_state, adapter = self.build_service(is_fake=True, mount_point=mount_point)

            self.assertEqual(service.mount_dashboard_drive(), "Local backup source connected.")
            self.assertTrue(fake_state.mounted)
            self.assertEqual(adapter.mounted, [])

    def test_real_mount_starts_related_services(self):
        with tempfile.TemporaryDirectory() as mount_point:
            service, _fake_state, adapter = self.build_service(mount_point=mount_point)

            self.assertEqual(
                service.mount_dashboard_drive(), "Drive mounted and available for use."
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

    def test_real_mount_prefers_managed_fstab_entry(self):
        with tempfile.TemporaryDirectory() as mount_point:
            service, _fake_state, adapter = self.build_service(mount_point=mount_point)

            with patch(
                "simple_safer_server.services.storage_service.get_managed_fstab_entry_for_mount_point",
                return_value={"uuid": "drive-uuid"},
            ):
                self.assertEqual(
                    service.mount_dashboard_drive(), "Drive mounted and available for use."
                )

            self.assertEqual(adapter.managed_mounted, [mount_point])
            self.assertEqual(adapter.mounted, [])

    def test_real_mount_rejects_stale_managed_fstab_uuid(self):
        with tempfile.TemporaryDirectory() as mount_point:
            service, _fake_state, adapter = self.build_service(mount_point=mount_point)

            with patch(
                "simple_safer_server.services.storage_service.get_managed_fstab_entry_for_mount_point",
                return_value={"uuid": "stale-uuid"},
            ):
                with self.assertRaisesRegex(ValidationProblem, "fstab entry does not match"):
                    service.mount_dashboard_drive()

            self.assertEqual(adapter.managed_mounted, [])
            self.assertEqual(adapter.mounted, [])

    def test_real_mount_reports_missing_uuid_without_system_commands(self):
        service, _fake_state, adapter = self.build_service(uuid=None)

        with self.assertRaisesRegex(ValidationProblem, "No drive UUID configured"):
            service.mount_dashboard_drive()
        self.assertEqual(adapter.mounted, [])

    def test_real_mount_uses_stable_error_message(self):
        with tempfile.TemporaryDirectory() as mount_point:
            service, _fake_state, adapter = self.build_service(mount_point=mount_point)
            adapter.raise_on_mount = subprocess.CalledProcessError(1, ["mount"])

            with self.assertRaisesRegex(OperationProblem, "Failed to mount drive\\."):
                service.mount_dashboard_drive()
