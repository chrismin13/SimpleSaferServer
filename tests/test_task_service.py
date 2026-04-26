import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from simple_safer_server.services.task_service import Status, TaskService


class FakeConfigManager:
    def __init__(self, mount_point):
        self.mount_point = mount_point

    def get_value(self, section, key, default=None):
        values = {
            ("backup", "mount_point"): self.mount_point,
            ("backup", "rclone_dir"): "",
            ("backup", "bandwidth_limit"): "",
            ("schedule", "backup_cloud_time"): "03:00",
        }
        return values.get((section, key), default)


class FakeState:
    def __init__(self):
        self.task_state = {}
        self.logs = []
        self.mounted = False

    def get_task_log(self, task_name):
        return (
            "\n".join(message for name, message in self.logs if name == task_name) or "No logs yet."
        )

    def append_task_log(self, task_name, message):
        self.logs.append((task_name, message))

    def set_task_state(self, task_name, **kwargs):
        self.task_state.setdefault(task_name, {}).update(kwargs)

    def get_task_state(self, task_name):
        return self.task_state.setdefault(
            task_name,
            {"status": Status.NOT_RUN_YET, "last_run": "", "last_run_duration": "-", "log": ""},
        )

    def get_next_run(self, task_name, backup_time):
        return f"{task_name} {backup_time}"

    def is_mounted(self, mount_point=None):
        return self.mounted

    def set_mount(self, mounted, mount_point=None):
        self.mounted = mounted


class TaskServiceTests(unittest.TestCase):
    def build_service(self, mount_point="/tmp/simple-safer-server-test"):
        runtime = SimpleNamespace(
            is_fake=True,
            default_mount_point=mount_point,
            repo_root=Path("."),
            rclone_config_dir=Path("."),
        )
        fake_state = FakeState()
        service = TaskService(
            runtime=runtime,
            config_manager=FakeConfigManager(mount_point),
            system_utils=MagicMock(),
            fake_state=fake_state,
            logger=MagicMock(),
        )
        return service, fake_state

    def test_get_task_returns_known_task_and_none_for_unknown_task(self):
        service, _fake_state = self.build_service()
        task = service.get_task("Cloud Backup")

        assert task is not None
        self.assertEqual(task.service_name, "backup_cloud.service")
        self.assertIsNone(service.get_task("Missing Task"))

    def test_task_summary_returns_error_fields_when_task_property_fails(self):
        service, _fake_state = self.build_service()
        task = service.get_task("Cloud Backup")
        assert task is not None

        task._service = MagicMock()
        task._service.get_next_run.side_effect = RuntimeError("boom")

        self.assertEqual(
            service.task_summary(task),
            {
                "name": "Cloud Backup",
                "next_run": "Error",
                "last_run": "Error",
                "status": "Error",
                "last_run_duration": "Error",
            },
        )

    def test_fake_duplicate_start_is_rejected(self):
        service, _fake_state = self.build_service()
        task = service.get_task("Cloud Backup")
        assert task is not None

        thread = threading.Thread(target=time.sleep, args=(0.2,))
        thread.start()
        service._fake_task_threads[task.name] = thread
        try:
            with self.assertRaisesRegex(RuntimeError, "Cloud Backup is already running"):
                task.start()
        finally:
            thread.join()

    def test_fake_stop_is_idempotent(self):
        service, fake_state = self.build_service()
        task = service.get_task("Cloud Backup")
        assert task is not None

        task.stop()

        self.assertEqual(fake_state.get_task_state("Cloud Backup")["status"], Status.STOPPED)
        self.assertIn(
            ("Cloud Backup", "Stop requested for Cloud Backup, but it was not running."),
            fake_state.logs,
        )
