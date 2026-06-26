import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from simple_safer_server.core.job_state import JobStateStore
from simple_safer_server.core.module_lifecycle import (
    module_apply_resources,
    ownership_manifest_for_runtime,
)
from simple_safer_server.modules.storage.location import marker_path
from simple_safer_server.services.task_service import (
    Status,
    TaskService,
    format_compact_schedule_datetime,
)


class FakeConfigManager:
    def __init__(self, mount_point, rclone_dir=""):
        self.mount_point = mount_point
        self.rclone_dir = rclone_dir
        self.storage_id = "test-storage-id"

    def get_all_config(self):
        return {
            "backup": {
                "mount_point": self.mount_point,
                "rclone_dir": self.rclone_dir,
                "bandwidth_limit": "",
                "cloud_enabled": "true",
            },
            "schedule": {"backup_cloud_time": "03:00"},
            "storage": {
                "mode": "existing_folder",
                "path": self.mount_point,
                "storage_id": self.storage_id,
            },
        }

    def get_value(self, section, key, default=None):
        values = {
            ("backup", "mount_point"): self.mount_point,
            ("backup", "rclone_dir"): self.rclone_dir,
            ("backup", "bandwidth_limit"): "",
            ("storage", "storage_id"): self.storage_id,
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
        rclone_dir="",
        applied_modules=("cloud-backup", "drive-health", "ddns", "storage"),
    ):
        data_dir = Path(tempfile.mkdtemp(prefix="sss-task-service-test-"))
        self.addCleanup(lambda: shutil.rmtree(data_dir, ignore_errors=True))
        runtime = SimpleNamespace(
            is_fake=is_fake,
            data_dir=data_dir,
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
        )
        manifest = ownership_manifest_for_runtime(runtime)
        for module_slug in applied_modules:
            module = service.module_registry.module_for_slug(module_slug)
            manifest.record_module_resources(module.slug, module_apply_resources(module))
        return service, fake_state

    def test_get_task_returns_known_task_and_none_for_unknown_task(self):
        service, _fake_state = self.build_service()
        task = service.get_task("Cloud Backup")

        assert task is not None
        self.assertEqual(task.worker_job_name, "cloud-backup")
        self.assertIsNone(service.get_task("Missing Task"))

    def test_task_summary_returns_error_fields_when_task_property_fails(self):
        service, _fake_state = self.build_service()
        task = service.get_task("Drive Health Check")
        assert task is not None

        service.schedule_state = MagicMock(side_effect=RuntimeError("boom"))

        self.assertEqual(
            service.task_summary(task),
            {
                "name": "Drive Health Check",
                "next_run": "Error",
                "last_run": "Error",
                "status": "Error",
                "last_run_duration": "Error",
                "schedule": {
                    "state": "issue",
                    "label": "Schedule issue",
                    "source": "system",
                    "raw": "boom",
                },
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

    def test_task_start_rejects_unapplied_module(self):
        service, _fake_state = self.build_service(applied_modules=())
        task = service.get_task("Cloud Backup")
        assert task is not None

        with self.assertRaisesRegex(RuntimeError, "Cloud Backup must be applied"):
            task.start()

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
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        source = Path(temp_dir.name) / "source"
        source.mkdir()
        marker = marker_path(source)
        marker.parent.mkdir(mode=0o700)
        marker.write_text('{"storage_id": "test-storage-id"}')
        service, fake_state = self.build_service(
            mount_point=str(source),
            rclone_dir=str(Path(temp_dir.name) / "fake-backup"),
        )
        service.rclone_adapter = MagicMock()
        service.rclone_adapter.sync.return_value = FakeProcess(stdout="copied\n")

        service._run_fake_cloud_backup(threading.Event())

        service.rclone_adapter.sync.assert_called_once()
        self.assertEqual(
            service.rclone_adapter.sync.call_args.kwargs["config_path"],
            "rclone.conf",
        )
        self.assertIn(
            ("Cloud Backup", "copied"),
            fake_state.logs,
        )

    @patch("simple_safer_server.services.task_service.run_scheduled_drive_health_check")
    def test_fake_drive_health_logs_smart_collection(self, mock_health_check):
        service, fake_state = self.build_service(mount_point=".")
        mock_health_check.return_value = {
            "smart": {"smart_194_raw": 31.0},
            "hdsentinel": {"snapshot": {"available": False}},
        }

        service._run_fake_drive_health_check("Drive Health", threading.Event())

        self.assertIn(("Drive Health", "SMART details collected."), fake_state.logs)

    @patch("simple_safer_server.services.task_service.run_ddns_update", return_value=0)
    def test_fake_ddns_update_runs_provider_module_for_parity(self, mock_update):
        service, fake_state = self.build_service()

        service._run_fake_ddns_update("DDNS Update", threading.Event())

        mock_update.assert_called_once_with()
        self.assertIn(
            ("DDNS Update", "DDNS update exited with code 0."),
            fake_state.logs,
        )

    def test_real_drive_health_task_reads_worker_job_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service, _fake_state = self.build_service(
                is_fake=False,
            )
            service.job_state_store = JobStateStore(SimpleNamespace(data_dir=Path(temp_dir)))
            service.job_state_store.path.write_text(
                json.dumps(
                    {
                        "jobs": {
                            "drive-health": {
                                "status": Status.SUCCESS,
                                "message": "Job completed successfully.",
                                "last_run": "2026-01-01T12:00:00+00:00",
                                "last_duration_seconds": 3,
                                "last_exit_code": 0,
                                "next_run_at": "2026-01-02T02:58:00+00:00",
                            }
                        }
                    }
                )
            )
            task = service.get_task("Drive Health Check")
            assert task is not None

            self.assertEqual(task.next_run, "2026-01-02T02:58:00+00:00")
            self.assertEqual(task.last_run, "2026-01-01T12:00:00+00:00")
            self.assertEqual(task.last_run_duration, "3s")
            self.assertEqual(task.status, Status.SUCCESS)
            self.assertIn("Job: Drive Health", task.get_logs())

    def test_real_worker_task_start_uses_worker_and_stop_is_not_supported(self):
        service, _fake_state = self.build_service(
            is_fake=False,
        )
        service.command_runner = MagicMock()
        task = service.get_task("Drive Health Check")
        assert task is not None

        task.start()

        command = service.command_runner.popen.call_args.args[0]
        self.assertEqual(command[-2:], ["--run-job", "drive-health"])
        with self.assertRaisesRegex(RuntimeError, "worker"):
            task.stop()

    def test_real_ddns_task_reads_worker_job_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service, _fake_state = self.build_service(
                is_fake=False,
            )
            service.job_state_store = JobStateStore(SimpleNamespace(data_dir=Path(temp_dir)))
            service.job_state_store.path.write_text(
                json.dumps(
                    {
                        "jobs": {
                            "ddns-update": {
                                "status": Status.SUCCESS,
                                "message": "Job completed successfully.",
                                "last_run": "2026-01-01T12:00:00+00:00",
                                "last_duration_seconds": 4,
                                "last_exit_code": 0,
                                "next_run_at": "2026-01-01T12:05:00+00:00",
                            }
                        }
                    }
                )
            )
            task = service.get_task("DDNS Update")
            assert task is not None

            self.assertEqual(task.status, Status.SUCCESS)
            self.assertEqual(task.last_run, "2026-01-01T12:00:00+00:00")
            self.assertEqual(task.last_run_duration, "4s")
            self.assertEqual(task.next_run, "2026-01-01T12:05:00+00:00")
            self.assertEqual(service.schedule_state(task)["source"], "worker")
            self.assertIn("Job: DDNS Update", task.get_logs())

    def test_real_ddns_task_start_runs_worker_job(self):
        service, _fake_state = self.build_service(is_fake=False)
        service.command_runner = MagicMock()
        task = service.get_task("DDNS Update")
        assert task is not None

        task.start()

        command = service.command_runner.popen.call_args.args[0]
        self.assertEqual(command[-2:], ["--run-job", "ddns-update"])

    def test_worker_schedules_do_not_use_disabled_timer_controls(self):
        service, _fake_state = self.build_service(is_fake=False)
        task = service.get_task("Drive Health Check")
        assert task is not None

        state = service.schedule_state(task)
        self.assertEqual(state["source"], "worker")
        self.assertNotIn("can_disable", state)
        self.assertNotIn("can_enable", state)

    def test_utc_schedule_label_uses_local_clock(self):
        if not hasattr(time, "tzset"):
            self.skipTest("tzset is required for local timezone label checks")
        original_tz = os.environ.get("TZ")
        os.environ["TZ"] = "America/New_York"
        time.tzset()
        try:
            service, _fake_state = self.build_service()
            local_target = (
                datetime.now().astimezone().replace(hour=8, minute=0, second=0, microsecond=0)
            )

            self.assertEqual(
                service._format_compact_datetime(local_target.astimezone(UTC)),
                "08:00",
            )
        finally:
            if original_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original_tz
            time.tzset()

    def test_schedule_datetime_labels_cover_today_tomorrow_and_later_dates(self):
        now = datetime(2026, 5, 13, 9, 0, 0, tzinfo=UTC)

        self.assertEqual(
            format_compact_schedule_datetime(datetime(2026, 5, 13, 18, 0, 0), now),
            "18:00",
        )
        self.assertEqual(
            format_compact_schedule_datetime(datetime(2026, 5, 14, 18, 0, 0), now),
            "Tomorrow 18:00",
        )
        self.assertEqual(
            format_compact_schedule_datetime(datetime(2026, 5, 16, 18, 0, 0), now),
            "May 16 18:00",
        )
