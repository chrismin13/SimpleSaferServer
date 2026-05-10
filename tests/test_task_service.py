import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from simple_safer_server.services.task_service import TASK_LOG_LINE_LIMIT, Status, TaskService


class FakeConfigManager:
    def __init__(self, mount_point, rclone_dir=""):
        self.mount_point = mount_point
        self.rclone_dir = rclone_dir

    def get_value(self, section, key, default=None):
        values = {
            ("backup", "mount_point"): self.mount_point,
            ("backup", "rclone_dir"): self.rclone_dir,
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


class FakeSystemdAdapter:
    def __init__(self):
        self.started = []
        self.stopped = []
        self.journal_output = "journal output"
        self.properties = {
            ("backup_cloud.timer", "NextElapseUSecRealtime"): (
                "NextElapseUSecRealtime=Mon 2026-04-27 03:00:00 UTC"
            ),
            ("backup_cloud.service", "ExecMainStartTimestamp"): (
                "ExecMainStartTimestamp=Sun 2026-04-26 03:00:00 UTC"
            ),
            ("backup_cloud.service", "LoadState"): "LoadState=loaded",
            ("backup_cloud.service", "Result"): "Result=success",
        }
        self.multi_properties = {
            "backup_cloud.service": (
                "ExecMainStartTimestampMonotonic=1000000\nExecMainExitTimestampMonotonic=4000000\n"
            )
        }
        self.active = "inactive"
        self.journal_calls = []

    def journal(self, unit_name, lines):
        self.journal_calls.append((unit_name, lines))
        return self.journal_output

    def start_unit(self, unit_name):
        self.started.append(unit_name)

    def stop_unit(self, unit_name):
        self.stopped.append(unit_name)

    def show_property(self, unit_name, property_name):
        return self.properties[(unit_name, property_name)]

    def show_properties(self, unit_name, *property_names):
        return self.multi_properties[unit_name]

    def is_active(self, unit_name):
        return self.active


class FakeProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        from io import StringIO

        self.returncode = returncode
        self.stdout = StringIO(stdout)
        self.stderr = StringIO(stderr)
        self._polled = False
        self.terminated = False
        self.killed = False

    def poll(self):
        if self._polled:
            return self.returncode
        self._polled = True
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


class TaskServiceTests(unittest.TestCase):
    def build_service(
        self,
        mount_point="/tmp/simple-safer-server-test",
        *,
        is_fake=True,
        systemd_adapter=None,
        rclone_dir="",
    ):
        runtime = SimpleNamespace(
            is_fake=is_fake,
            default_mount_point=mount_point,
            repo_root=Path("."),
            rclone_config_dir=Path("."),
        )
        fake_state = FakeState()
        service = TaskService(
            runtime=runtime,
            config_manager=FakeConfigManager(mount_point, rclone_dir=rclone_dir),
            system_utils=MagicMock(),
            fake_state=fake_state,
            logger=MagicMock(),
            systemd_adapter=systemd_adapter,
        )
        return service, fake_state

    def test_get_task_returns_known_task_and_none_for_unknown_task(self):
        service, _fake_state = self.build_service()
        task = service.get_task("Cloud Backup")

        assert task is not None
        self.assertEqual(task.service_name, "backup_cloud.service")
        app_update = service.get_task("App Update")
        assert app_update is not None
        self.assertEqual(app_update.service_name, "app_update.service")
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

    def test_fake_stop_leaves_initial_idle_state_unchanged(self):
        service, fake_state = self.build_service()
        task = service.get_task("Cloud Backup")
        assert task is not None

        task.stop()

        self.assertEqual(fake_state.get_task_state("Cloud Backup")["status"], Status.NOT_RUN_YET)
        self.assertIn(
            ("Cloud Backup", "Stop requested for Cloud Backup, but it was not running."),
            fake_state.logs,
        )

    def test_fake_stop_does_not_clobber_completed_task(self):
        service, fake_state = self.build_service()
        task = service.get_task("Cloud Backup")
        assert task is not None
        fake_state.set_task_state("Cloud Backup", status=Status.SUCCESS)

        task.stop()

        self.assertEqual(fake_state.get_task_state("Cloud Backup")["status"], Status.SUCCESS)

    def test_fake_cloud_backup_runs_rclone_for_provider_parity(self):
        service, fake_state = self.build_service(mount_point=".", rclone_dir="/tmp/fake-backup")
        service.rclone_adapter = MagicMock()
        service.rclone_adapter.sync.return_value = FakeProcess(stdout="copied\n")

        service._run_fake_cloud_backup(threading.Event())

        service.rclone_adapter.sync.assert_called_once()
        self.assertIn(
            ("Cloud Backup", "copied"),
            fake_state.logs,
        )

    def test_fake_ddns_update_runs_provider_script_for_parity(self):
        service, fake_state = self.build_service()
        service.command_runner = MagicMock()
        service.command_runner.popen.return_value = FakeProcess(stdout="updated\n")

        service._run_fake_ddns_update("DDNS Update", threading.Event())

        service.command_runner.popen.assert_called_once()
        self.assertIn(
            ("DDNS Update", "updated"),
            fake_state.logs,
        )

    def test_real_task_status_and_timestamps_use_systemd_adapter(self):
        systemd_adapter = FakeSystemdAdapter()
        service, _fake_state = self.build_service(is_fake=False, systemd_adapter=systemd_adapter)
        task = service.get_task("Cloud Backup")
        assert task is not None

        self.assertEqual(
            task.next_run,
            "Mon 2026-04-27 03:00:00 UTC",
        )
        self.assertEqual(task.last_run, "Sun 2026-04-26 03:00:00 UTC")
        self.assertEqual(task.last_run_duration, "3s")
        self.assertEqual(task.status, Status.SUCCESS)

    def test_real_task_start_stop_and_logs_use_systemd_adapter(self):
        systemd_adapter = FakeSystemdAdapter()
        service, _fake_state = self.build_service(is_fake=False, systemd_adapter=systemd_adapter)
        task = service.get_task("Cloud Backup")
        assert task is not None

        task.start()
        task.stop()

        self.assertEqual(task.get_logs(), "journal output")
        self.assertEqual(
            systemd_adapter.journal_calls,
            [("backup_cloud.service", TASK_LOG_LINE_LIMIT)],
        )
        self.assertEqual(systemd_adapter.started, ["backup_cloud.service"])
        self.assertEqual(systemd_adapter.stopped, ["backup_cloud.service"])
