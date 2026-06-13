import json
import os
import threading
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from simple_safer_server.services.task_service import (
    TASK_LOG_LINE_LIMIT,
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
            },
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


class FakeSystemdAdapter:
    def __init__(self):
        self.started = []
        self.stopped = []
        self.disabled_timers = []
        self.enabled_timers = []
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
            ("backup_cloud.timer", "UnitFileState"): "UnitFileState=enabled",
            ("backup_cloud.timer", "LoadState"): "LoadState=loaded",
            ("backup_cloud.timer", "ActiveState"): "ActiveState=active",
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

    def disable_timer_now(self, unit_name):
        self.disabled_timers.append(unit_name)

    def enable_timer_now(self, unit_name):
        self.enabled_timers.append(unit_name)

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
            data_dir=Path("/tmp/simple-safer-server-test-data"),
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

        service.get_next_run = MagicMock(side_effect=RuntimeError("boom"))

        self.assertEqual(
            service.task_summary(task),
            {
                "name": "Cloud Backup",
                "next_run": "Error",
                "last_run": "Error",
                "status": "Error",
                "last_run_duration": "Error",
                "schedule": {
                    "state": "issue",
                    "label": "Schedule issue",
                    "source": "system",
                    "raw": "boom",
                    "can_disable": True,
                    "can_enable": True,
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
        marker_dir = Path(".simple-safer-server")
        marker_dir.mkdir(exist_ok=True)
        self.addCleanup(lambda: marker_dir.rmdir() if marker_dir.exists() else None)
        self.addCleanup(lambda: (marker_dir / "storage.json").unlink(missing_ok=True))
        (marker_dir / "storage.json").write_text('{"storage_id": "test-storage-id"}')
        service.rclone_adapter = MagicMock()
        service.rclone_adapter.sync.return_value = FakeProcess(stdout="copied\n")

        service._run_fake_cloud_backup(threading.Event())

        service.rclone_adapter.sync.assert_called_once()
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

    def test_disable_schedule_disables_timer_not_service_and_manual_start_still_works(self):
        systemd_adapter = FakeSystemdAdapter()
        service, _fake_state = self.build_service(is_fake=False, systemd_adapter=systemd_adapter)
        task = service.get_task("Cloud Backup")
        assert task is not None

        service.disable_schedule(task, "permanent")
        task.start()

        self.assertEqual(systemd_adapter.disabled_timers, ["backup_cloud.timer"])
        self.assertEqual(systemd_adapter.started, ["backup_cloud.service"])

    def test_enable_schedule_enables_timer_and_clears_schedule_state(self):
        systemd_adapter = FakeSystemdAdapter()
        service, _fake_state = self.build_service(is_fake=False, systemd_adapter=systemd_adapter)
        task = service.get_task("Cloud Backup")
        assert task is not None

        service.disable_schedule(task, "permanent")
        service.enable_schedule(task)

        self.assertEqual(systemd_adapter.enabled_timers, ["backup_cloud.timer"])
        self.assertEqual(service.schedule_state(task)["state"], "active")

    def test_schedule_state_reports_managed_external_and_issue_states(self):
        systemd_adapter = FakeSystemdAdapter()
        service, _fake_state = self.build_service(is_fake=False, systemd_adapter=systemd_adapter)
        task = service.get_task("Cloud Backup")
        assert task is not None

        service.disable_schedule(task, "permanent")
        self.assertEqual(service.schedule_state(task)["label"], "Disabled")

        service.enable_schedule(task)
        systemd_adapter.properties[("backup_cloud.timer", "UnitFileState")] = (
            "UnitFileState=disabled"
        )
        self.assertEqual(service.schedule_state(task)["label"], "Disabled externally")

        systemd_adapter.properties[("backup_cloud.timer", "UnitFileState")] = "UnitFileState=bad"
        self.assertEqual(service.schedule_state(task)["label"], "Schedule issue")

    def test_temporary_schedule_state_uses_compact_disable_label(self):
        systemd_adapter = FakeSystemdAdapter()
        service, _fake_state = self.build_service(is_fake=False, systemd_adapter=systemd_adapter)
        task = service.get_task("Cloud Backup")
        assert task is not None

        service.disable_schedule(task, "temporary", hours=6)

        self.assertTrue(service.schedule_state(task)["label"].startswith("Disabled until "))

    def test_malformed_temporary_schedule_state_still_allows_reenable(self):
        systemd_adapter = FakeSystemdAdapter()
        service, _fake_state = self.build_service(is_fake=False, systemd_adapter=systemd_adapter)
        task = service.get_task("Cloud Backup")
        assert task is not None
        service.disabled_timer_service.path.parent.mkdir(parents=True, exist_ok=True)
        service.disabled_timer_service.path.write_text(
            json.dumps(
                {
                    "backup_cloud.timer": {
                        "task_name": "Cloud Backup",
                        "timer_name": "backup_cloud.timer",
                        "mode": "temporary",
                        "created_at": "2026-05-13T12:00:00+00:00",
                        "expires_at": "2026-05-13T18:00:00",
                        "restore_attempts": 0,
                        "restore_failed": False,
                    }
                }
            )
        )

        state = service.schedule_state(task)

        self.assertEqual(state["label"], "Disabled")
        self.assertTrue(state["can_enable"])

    def test_utc_disabled_timer_label_uses_local_clock(self):
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
