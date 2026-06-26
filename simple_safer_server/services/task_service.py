import os
import queue
import sys
import threading
import time
from datetime import datetime, timedelta
from typing import Any

from simple_safer_server.adapters.command_runner import (
    DEVNULL,
    CommandRunner,
    TimeoutExpired,
)
from simple_safer_server.adapters.rclone import RcloneAdapter
from simple_safer_server.core.builtin_modules import create_builtin_module_registry
from simple_safer_server.core.job_lifecycle import (
    job_module_is_applied,
    require_job_module_applied,
)
from simple_safer_server.core.job_state import (
    JobStateStore,
    daily_time_with_offset,
    format_timestamp,
    next_daily_run_after,
    parse_timestamp,
)
from simple_safer_server.core.jobs import JobDefinition, create_builtin_job_registry
from simple_safer_server.core.module_contract import ModuleRegistry
from simple_safer_server.modules.ddns.updater import main as run_ddns_update
from simple_safer_server.modules.drive_health.service import (
    hdsentinel_snapshot_has_health,
    run_scheduled_drive_health_check,
)
from simple_safer_server.modules.storage.location import validate_storage_ready_for_backup


class Status:
    RUNNING = "Running"
    SUCCESS = "Success"
    FAILURE = "Failure"
    MISSING = "Missing"
    NOT_RUN_YET = "Not Run Yet"
    ERROR = "Error"
    STOPPED = "Stopped"


TERMINAL_FAKE_STATUSES = {Status.SUCCESS, Status.FAILURE, Status.ERROR, Status.STOPPED}

# Keep one app-wide task-log window so routes, auto-refresh, and service defaults
# do not quietly drift apart after job output grows or shrinks.
TASK_LOG_LINE_LIMIT = 500


def format_compact_schedule_datetime(value: datetime | None, now: datetime) -> str:
    if value is None:
        return "Unknown"
    if value.date() == now.date():
        return value.strftime("%H:%M")
    if value.date() == (now + timedelta(days=1)).date():
        return "Tomorrow {}".format(value.strftime("%H:%M"))
    return value.strftime("%b %-d %H:%M")


def clamp_task_log_lines(lines: Any) -> int:
    try:
        parsed_lines = int(lines)
    except TypeError, ValueError:
        parsed_lines = TASK_LOG_LINE_LIMIT
    return max(1, min(parsed_lines, TASK_LOG_LINE_LIMIT))


class Task:
    def __init__(
        self,
        service: TaskService,
        name: str,
        worker_job_name: str,
    ):
        self._service = service
        self.name = name
        self.worker_job_name = worker_job_name

    def get_logs(self, lines: int = TASK_LOG_LINE_LIMIT) -> str:
        """Return the latest systemd journal logs for this service."""
        return self._service.get_logs(self, lines)

    def start(self) -> None:
        """Start the associated service asynchronously."""
        self._service.start_task(self)

    def stop(self) -> None:
        """Stop the associated service asynchronously."""
        self._service.stop_task(self)

    @property
    def next_run(self) -> str:
        return self._service.get_next_run(self)

    @property
    def last_run(self) -> str:
        return self._service.get_last_run(self)

    @property
    def last_run_duration(self) -> str:
        return self._service.get_last_run_duration(self)

    @property
    def status(self) -> str:
        return self._service.get_status(self)


class TaskService:
    def __init__(
        self,
        runtime: Any,
        config_manager: Any,
        system_utils: Any,
        fake_state: Any | None = None,
        logger: Any | None = None,
        command_runner: CommandRunner | None = None,
        rclone_adapter: RcloneAdapter | None = None,
        job_state_store: JobStateStore | None = None,
        module_registry: ModuleRegistry | None = None,
    ):
        self.runtime = runtime
        self.config_manager = config_manager
        self.system_utils = system_utils
        self.fake_state = fake_state
        self.logger = logger
        self.command_runner = command_runner or CommandRunner()
        self.rclone_adapter = rclone_adapter or RcloneAdapter(self.command_runner)
        self.module_registry = module_registry or create_builtin_module_registry()
        self.job_registry = create_builtin_job_registry()
        self.job_state_store = job_state_store or JobStateStore(runtime)
        self._fake_task_threads: dict[str, threading.Thread] = {}
        self._fake_task_cancel_events: dict[str, threading.Event] = {}
        self._fake_task_lock = threading.Lock()
        self._tasks = [
            Task(
                self,
                "Check Mount",
                worker_job_name="mount-check",
            ),
            Task(
                self,
                "Drive Health Check",
                worker_job_name="drive-health",
            ),
            Task(
                self,
                "Cloud Backup",
                worker_job_name="cloud-backup",
            ),
            Task(
                self,
                "DDNS Update",
                worker_job_name="ddns-update",
            ),
        ]

    def get_task(self, name: str) -> Task | None:
        for task in self._tasks:
            if task.name == name:
                return task
        return None

    def task_summary(self, task: Task) -> dict[str, Any]:
        try:
            schedule = self.schedule_state(task)
            return {
                "name": task.name,
                "next_run": schedule["label"],
                "last_run": task.last_run,
                "status": task.status,
                "last_run_duration": task.last_run_duration,
                "schedule": schedule,
            }
        except Exception as exc:
            if self.logger:
                self.logger.warning("Error getting task info for %s: %s", task.name, exc)
            return {
                "name": task.name,
                "next_run": "Error",
                "last_run": "Error",
                "status": "Error",
                "last_run_duration": "Error",
                "schedule": {
                    "state": "issue",
                    "label": "Schedule issue",
                    "source": "system",
                    "raw": str(exc),
                },
            }

    def task_summaries(self) -> list[dict[str, Any]]:
        return [self.task_summary(task) for task in self._tasks]

    def get_check_mount_next_run(self) -> str | None:
        check_mount_task = self.get_task("Check Mount")
        if not check_mount_task:
            return None
        return self.schedule_state(check_mount_task)["raw_next_run"]

    def _require_fake_state(self) -> Any:
        if self.fake_state is None:
            raise RuntimeError("Fake task state is not available.")
        return self.fake_state

    def get_logs(self, task: Task, lines: int = TASK_LOG_LINE_LIMIT) -> str:
        if self.runtime.is_fake:
            return self._require_fake_state().get_task_log(task.name)
        return self.job_state_store.task_log(self._worker_job_definition(task))

    def start_task(self, task: Task) -> None:
        self._require_worker_job_module_applied(task)
        if self.runtime.is_fake:
            self._start_fake_task(task.name)
            return
        try:
            self.command_runner.popen(
                [
                    sys.executable,
                    "-m",
                    "simple_safer_server.worker",
                    "--run-job",
                    task.worker_job_name,
                ],
                stdout=DEVNULL,
                stderr=DEVNULL,
                start_new_session=True,
            )
            return
        except Exception as exc:
            raise RuntimeError(f"Failed to start worker job {task.worker_job_name}: {exc}") from exc

    def stop_task(self, task: Task) -> None:
        if self.runtime.is_fake:
            fake_state = self._require_fake_state()
            with self._fake_task_lock:
                thread = self._fake_task_threads.get(task.name)
                cancel_event = self._fake_task_cancel_events.get(task.name)
                is_running = bool(thread and thread.is_alive() and cancel_event)
                if is_running and cancel_event is not None:
                    cancel_event.set()
            if is_running:
                fake_state.append_task_log(task.name, f"Stopped {task.name} in fake mode.")
            else:
                fake_state.append_task_log(
                    task.name,
                    f"Stop requested for {task.name}, but it was not running.",
                )
            # Stop is idempotent because the UI may retry after a timeout or page refresh.
            current_status = fake_state.get_task_state(task.name).get("status")
            if is_running or (
                current_status != Status.NOT_RUN_YET
                and current_status not in TERMINAL_FAKE_STATUSES
            ):
                fake_state.set_task_state(task.name, status=Status.STOPPED)
            return
        raise RuntimeError(f"{task.name} runs through the worker and cannot be stopped here.")

    def schedule_state(self, task: Task) -> dict[str, Any]:
        return self._worker_schedule_state(task)

    def _worker_job_definition(self, task: Task) -> JobDefinition:
        return self.job_registry.job_for_name(task.worker_job_name)

    def _require_worker_job_module_applied(self, task: Task) -> None:
        require_job_module_applied(
            self._worker_job_definition(task),
            module_registry=self.module_registry,
            runtime=self.runtime,
        )

    def _worker_job_module_is_applied(self, task: Task) -> bool:
        return job_module_is_applied(
            self._worker_job_definition(task),
            module_registry=self.module_registry,
            runtime=self.runtime,
        )

    def _worker_schedule_state(self, task: Task) -> dict[str, Any]:
        job = self._worker_job_definition(task)
        if not self._worker_job_module_is_applied(task):
            return {
                "state": "setup-required",
                "label": "Setup required",
                "source": "simple_safer_server",
                "raw_next_run": "Setup required",
            }
        if not job.is_worker_scheduled:
            return {
                "state": "manual",
                "label": "Manual only",
                "source": "simple_safer_server",
                "raw_next_run": "Manual only",
            }
        config = self.config_manager.get_all_config()
        if not job.is_enabled(config):
            return {
                "state": "disabled",
                "label": "Disabled",
                "source": "simple_safer_server",
                "raw_next_run": "Disabled",
            }
        state = self.job_state_store.job(job.name)
        next_run_at = parse_timestamp(state.get("next_run_at"))
        status = state.get("status", "Not Run Yet")
        if next_run_at is None and job.is_daily_scheduled:
            next_run_at = next_daily_run_after(
                datetime.now().astimezone(),
                daily_time_with_offset(
                    job.daily_time_from_config(config),
                    job.daily_time_offset_minutes,
                ),
            )
            raw_next_run = format_timestamp(next_run_at)
        else:
            raw_next_run = state.get("next_run_at")
        if next_run_at is None:
            label = "Due now"
            raw_next_run = "Due now"
        else:
            label = self._format_compact_datetime(next_run_at)
        return {
            "state": "running" if status == Status.RUNNING else "active",
            "label": "Running" if status == Status.RUNNING else label,
            "source": "worker",
            "raw_next_run": raw_next_run,
            "interval_seconds": job.interval_seconds,
        }

    def _format_compact_datetime(self, value: datetime | None) -> str:
        if value is not None and value.tzinfo is not None:
            value = value.astimezone().replace(tzinfo=None)
        return format_compact_schedule_datetime(value, datetime.now())

    def get_next_run(self, task: Task) -> str:
        return self._worker_schedule_state(task)["raw_next_run"]

    def get_last_run(self, task: Task) -> str:
        if self.runtime.is_fake:
            task_state = self._require_fake_state().get_task_state(task.name)
            return task_state.get("last_run") or "Not Run Yet"
        return self.job_state_store.job(task.worker_job_name).get("last_run") or "Not Run Yet"

    def get_last_run_duration(self, task: Task) -> str:
        if self.runtime.is_fake:
            task_state = self._require_fake_state().get_task_state(task.name)
            return task_state.get("last_run_duration", "-")
        duration = self.job_state_store.job(task.worker_job_name).get("last_duration_seconds")
        if duration is None:
            return "-"
        return f"{duration}s"

    def get_status(self, task: Task) -> str:
        if self.runtime.is_fake:
            task_state = self._require_fake_state().get_task_state(task.name)
            return task_state.get("status", Status.NOT_RUN_YET)
        return self.job_state_store.job(task.worker_job_name).get("status", Status.NOT_RUN_YET)

    def _run_fake_cloud_backup(self, cancel_event: threading.Event) -> None:
        fake_state = self._require_fake_state()
        source = self.config_manager.get_value(
            "backup",
            "mount_point",
            self.runtime.default_mount_point,
        )
        destination = self.config_manager.get_value("backup", "rclone_dir", "").strip()
        rclone_config_path = self.runtime.rclone_config_dir / "rclone.conf"
        if not source:
            raise RuntimeError("No source folder configured.")
        if not os.path.isdir(source):
            raise RuntimeError(f"Source folder does not exist: {source}")
        validate_storage_ready_for_backup(
            self.config_manager,
            self.system_utils,
            runtime=self.runtime,
            command_runner=self.command_runner,
        )
        if not destination:
            raise RuntimeError("No cloud destination configured.")
        if ":" in destination and not rclone_config_path.exists():
            raise RuntimeError(f"Rclone config not found at {rclone_config_path}")

        fake_state.append_task_log(
            "Cloud Backup",
            f"Starting backup from {source} to {destination}",
        )
        bandwidth_limit = self.config_manager.get_value("backup", "bandwidth_limit", "").strip()
        proc = self.rclone_adapter.sync(
            source,
            destination,
            config_path=str(rclone_config_path),
            bandwidth_limit=bandwidth_limit,
        )
        stdout_output, stderr_output = self._collect_process_output(
            proc, cancel_event, "fake-cloud-backup"
        )
        output = f"{stdout_output}{stderr_output}"
        if output.strip():
            fake_state.append_task_log("Cloud Backup", output.strip())
        if cancel_event.is_set():
            raise RuntimeError("Cloud backup was cancelled.")
        if proc.returncode != 0:
            raise RuntimeError(output.strip() or "Cloud backup failed.")

    def _start_fake_task(self, task_name: str) -> None:
        fake_state = self._require_fake_state()
        with self._fake_task_lock:
            existing_thread = self._fake_task_threads.get(task_name)
            if existing_thread and existing_thread.is_alive():
                raise RuntimeError(f"{task_name} is already running.")

            cancel_event = threading.Event()
            self._fake_task_cancel_events[task_name] = cancel_event

            fake_state.set_task_state(task_name, status=Status.RUNNING)
            fake_state.append_task_log(task_name, f"Starting {task_name} in fake mode.")

            thread = threading.Thread(
                target=self._run_fake_task,
                args=(task_name, cancel_event),
                name="fake-task-{}".format(task_name.lower().replace(" ", "-")),
                daemon=True,
            )
            self._fake_task_threads[task_name] = thread
            thread.start()

    def _run_fake_task(self, task_name: str, cancel_event: threading.Event) -> None:
        fake_state = self._require_fake_state()
        start_time = datetime.now()
        try:
            if task_name == "Check Mount":
                self._run_fake_check_mount(task_name, cancel_event)
            elif task_name == "Drive Health Check":
                self._run_fake_drive_health_check(task_name, cancel_event)
            elif task_name == "Cloud Backup":
                self._run_fake_cloud_backup(cancel_event)
            elif task_name == "DDNS Update":
                self._run_fake_ddns_update(task_name, cancel_event)

            if cancel_event.is_set():
                raise RuntimeError("Task was cancelled.")

            duration = max(0, int((datetime.now() - start_time).total_seconds()))
            fake_state.set_task_state(
                task_name,
                status=Status.SUCCESS,
                last_run=start_time.strftime("%Y-%m-%d %H:%M:%S"),
                last_run_duration=f"{duration}s",
            )
            fake_state.append_task_log(task_name, f"{task_name} finished successfully.")
        except Exception as exc:
            duration = max(0, int((datetime.now() - start_time).total_seconds()))
            if cancel_event.is_set():
                fake_state.set_task_state(
                    task_name,
                    status=Status.STOPPED,
                    last_run=start_time.strftime("%Y-%m-%d %H:%M:%S"),
                    last_run_duration=f"{duration}s",
                )
            else:
                fake_state.set_task_state(
                    task_name,
                    status=Status.FAILURE,
                    last_run=start_time.strftime("%Y-%m-%d %H:%M:%S"),
                    last_run_duration=f"{duration}s",
                )
                fake_state.append_task_log(task_name, f"{task_name} failed: {exc}")
                if self.logger:
                    self.logger.warning("Fake task %s failed: %s", task_name, exc)
        finally:
            with self._fake_task_lock:
                active_thread = self._fake_task_threads.get(task_name)
                if active_thread is threading.current_thread():
                    self._fake_task_threads.pop(task_name, None)
                    self._fake_task_cancel_events.pop(task_name, None)

    def _run_fake_check_mount(self, task_name: str, cancel_event: threading.Event) -> None:
        fake_state = self._require_fake_state()
        mount_point = self.config_manager.get_value(
            "backup",
            "mount_point",
            self.runtime.default_mount_point,
        )
        if not os.path.isdir(mount_point):
            raise RuntimeError(f"Backup source folder not found: {mount_point}")
        if cancel_event.is_set():
            raise RuntimeError("Task was cancelled.")
        if not fake_state.is_mounted(mount_point):
            fake_state.set_mount(True, mount_point=mount_point)
            fake_state.append_task_log(
                task_name,
                f"Found local backup source at {mount_point}; marking it as connected.",
            )
        fake_state.append_task_log(task_name, f"Backup source available at {mount_point}.")

    def _run_fake_drive_health_check(self, task_name: str, cancel_event: threading.Event) -> None:
        fake_state = self._require_fake_state()
        if cancel_event.is_set():
            raise RuntimeError("Task was cancelled.")
        result = run_scheduled_drive_health_check(
            self.config_manager,
            self.system_utils,
            runtime=self.runtime,
        )
        if result.get("smart") is not None:
            fake_state.append_task_log(task_name, "SMART details collected.")

        hdsentinel_snapshot = result.get("hdsentinel", {}).get("snapshot")
        if hdsentinel_snapshot_has_health(hdsentinel_snapshot):
            fake_state.append_task_log(
                task_name,
                ("HDSentinel status: health {}%, performance {}%, temperature {}C").format(
                    hdsentinel_snapshot.get("health_pct"),
                    hdsentinel_snapshot.get("performance_pct"),
                    hdsentinel_snapshot.get("temperature_c"),
                ),
            )
        elif hdsentinel_snapshot and hdsentinel_snapshot.get("error"):
            fake_state.append_task_log(
                task_name,
                "HDSentinel unavailable: {}".format(hdsentinel_snapshot["error"]),
            )

    def _run_fake_ddns_update(self, task_name: str, cancel_event: threading.Event) -> None:
        fake_state = self._require_fake_state()
        if cancel_event.is_set():
            raise RuntimeError("Task was cancelled.")

        # Fake mode avoids local systemd, but DDNS itself is still a provider
        # integration that developers need to exercise against real test records.
        exit_code = int(run_ddns_update() or 0)
        fake_state.append_task_log(task_name, f"DDNS update exited with code {exit_code}.")
        if cancel_event.is_set():
            raise RuntimeError("Task was cancelled.")
        if exit_code != 0:
            raise RuntimeError(f"DDNS update exited with code {exit_code}.")

    def _collect_process_output(
        self,
        proc: Any,
        cancel_event: threading.Event,
        thread_name_prefix: str,
    ) -> tuple[str, str]:
        output_queue: queue.Queue[tuple[str, str]] = queue.Queue()

        def _drain_stream(stream: Any, stream_name: str) -> None:
            try:
                for line in iter(stream.readline, ""):
                    output_queue.put((stream_name, line))
            finally:
                stream.close()

        stdout_thread = threading.Thread(
            target=_drain_stream,
            args=(proc.stdout, "stdout"),
            name=f"{thread_name_prefix}-stdout",
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_drain_stream,
            args=(proc.stderr, "stderr"),
            name=f"{thread_name_prefix}-stderr",
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        while True:
            self._drain_output_queue(output_queue, stdout_chunks, stderr_chunks)
            if proc.poll() is not None:
                break
            if cancel_event.is_set():
                proc.terminate()
                try:
                    proc.wait(timeout=5.0)
                except TimeoutExpired:
                    proc.kill()
                    proc.wait()
                break
            time.sleep(0.1)

        stdout_thread.join(timeout=1.0)
        stderr_thread.join(timeout=1.0)
        self._drain_output_queue(output_queue, stdout_chunks, stderr_chunks)
        return "".join(stdout_chunks).strip(), "".join(stderr_chunks).strip()

    @staticmethod
    def _drain_output_queue(
        output_queue: Any, stdout_chunks: list[str], stderr_chunks: list[str]
    ) -> None:
        while True:
            try:
                stream_name, chunk = output_queue.get_nowait()
            except queue.Empty:
                break
            if stream_name == "stdout":
                stdout_chunks.append(chunk)
            else:
                stderr_chunks.append(chunk)
