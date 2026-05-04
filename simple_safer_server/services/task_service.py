import os
import queue
import sys
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from simple_safer_server.adapters.command_runner import (
    PIPE,
    CommandRunner,
    SubprocessError,
    TimeoutExpired,
)
from simple_safer_server.adapters.rclone import RcloneAdapter
from simple_safer_server.adapters.systemd import CalledProcessError, SystemdAdapter
from simple_safer_server.services.drive_health import run_scheduled_drive_health_check


class Status:
    RUNNING = "Running"
    SUCCESS = "Success"
    FAILURE = "Failure"
    MISSING = "Missing"
    NOT_RUN_YET = "Not Run Yet"
    ERROR = "Error"
    STOPPED = "Stopped"


TERMINAL_FAKE_STATUSES = {Status.SUCCESS, Status.FAILURE, Status.ERROR, Status.STOPPED}


class Task:
    def __init__(self, service: "TaskService", name: str, service_name: str, timer_name: str):
        self._service = service
        self.name = name
        self.service_name = service_name
        self.timer_name = timer_name

    def get_logs(self, lines: int = 50) -> str:
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
        fake_state: Optional[Any] = None,
        logger: Optional[Any] = None,
        command_runner: Optional[CommandRunner] = None,
        systemd_adapter: Optional[SystemdAdapter] = None,
        rclone_adapter: Optional[RcloneAdapter] = None,
    ):
        self.runtime = runtime
        self.config_manager = config_manager
        self.system_utils = system_utils
        self.fake_state = fake_state
        self.logger = logger
        self.command_runner = command_runner or CommandRunner()
        self.systemd_adapter = systemd_adapter or SystemdAdapter(self.command_runner)
        self.rclone_adapter = rclone_adapter or RcloneAdapter(self.command_runner)
        self._fake_task_threads = {}  # type: Dict[str, threading.Thread]
        self._fake_task_cancel_events = {}  # type: Dict[str, threading.Event]
        self._fake_task_lock = threading.Lock()
        self._tasks = [
            Task(self, "Check Mount", "check_mount.service", "check_mount.timer"),
            Task(self, "Drive Health Check", "check_health.service", "check_health.timer"),
            Task(self, "Cloud Backup", "backup_cloud.service", "backup_cloud.timer"),
            Task(self, "DDNS Update", "ddns_update.service", "ddns_update.timer"),
            Task(self, "App Update", "app_update.service", "app_update.timer"),
        ]

    def get_task(self, name: str) -> Optional[Task]:
        for task in self._tasks:
            if task.name == name:
                return task
        return None

    def task_summary(self, task: Task) -> Dict[str, str]:
        try:
            return {
                "name": task.name,
                "next_run": task.next_run,
                "last_run": task.last_run,
                "status": task.status,
                "last_run_duration": task.last_run_duration,
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
            }

    def task_summaries(self) -> List[Dict[str, str]]:
        return [self.task_summary(task) for task in self._tasks]

    def get_check_mount_next_run(self) -> Optional[str]:
        check_mount_task = self.get_task("Check Mount")
        if not check_mount_task:
            return None
        return check_mount_task.next_run

    def _require_fake_state(self) -> Any:
        if self.fake_state is None:
            raise RuntimeError("Fake task state is not available.")
        return self.fake_state

    def get_logs(self, task: Task, lines: int = 50) -> str:
        if self.runtime.is_fake:
            return self._require_fake_state().get_task_log(task.name)
        try:
            return self.systemd_adapter.journal(task.service_name, lines)
        except CalledProcessError:
            return "Retrieval Error"

    def start_task(self, task: Task) -> None:
        if self.runtime.is_fake:
            self._start_fake_task(task.name)
            return
        try:
            self.systemd_adapter.start_unit(task.service_name)
        except Exception as exc:
            raise RuntimeError(f"Failed to start {task.service_name}: {exc}") from exc

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
        try:
            self.systemd_adapter.stop_unit(task.service_name)
        except Exception as exc:
            raise RuntimeError(f"Failed to stop {task.service_name}: {exc}") from exc

    def get_next_run(self, task: Task) -> str:
        if self.runtime.is_fake:
            if task.name == "DDNS Update":
                # Fake-mode DDNS reports the next 5-minute boundary: start with
                # datetime.now(), round the minute via (now.minute // 5 + 1) * 5,
                # and let timedelta handle hour rollover when that reaches 60.
                # The UI expects a minute-precision "%Y-%m-%d %H:%M:00" string.
                now = datetime.now()
                minutes = (now.minute // 5 + 1) * 5
                next_run = now.replace(minute=0, second=0, microsecond=0) + timedelta(
                    minutes=minutes
                )
                return next_run.strftime("%Y-%m-%d %H:%M:00")
            if task.name == "App Update":
                backup_time = self.config_manager.get_value(
                    "schedule", "backup_cloud_time", "03:00"
                )
                return self._require_fake_state().get_next_run(task.name, backup_time or "03:00")
            backup_time = self.config_manager.get_value("schedule", "backup_cloud_time", "03:00")
            return self._require_fake_state().get_next_run(task.name, backup_time or "03:00")
        try:
            output = self.systemd_adapter.show_property(task.timer_name, "NextElapseUSecRealtime")
            if "=" in output:
                return output.split("=")[-1].strip()
            return "Unknown"
        except CalledProcessError:
            return "Retrieval Error"

    def get_last_run(self, task: Task) -> str:
        if self.runtime.is_fake:
            task_state = self._require_fake_state().get_task_state(task.name)
            return task_state.get("last_run") or "Not Run Yet"
        try:
            output = self.systemd_adapter.show_property(task.service_name, "ExecMainStartTimestamp")
            if "=" in output:
                return output.split("=")[-1].strip()
            return "Unknown"
        except CalledProcessError:
            return "Retrieval Error"

    def get_last_run_duration(self, task: Task) -> str:
        if self.runtime.is_fake:
            task_state = self._require_fake_state().get_task_state(task.name)
            return task_state.get("last_run_duration", "-")
        try:
            output = self.systemd_adapter.show_properties(
                task.service_name,
                "ExecMainStartTimestampMonotonic",
                "ExecMainExitTimestampMonotonic",
            )
            start = exit_ts = None
            for line in output.splitlines():
                if line.startswith("ExecMainStartTimestampMonotonic="):
                    value = line.split("=", 1)[1].strip()
                    if value:
                        start = int(value)
                elif line.startswith("ExecMainExitTimestampMonotonic="):
                    value = line.split("=", 1)[1].strip()
                    if value:
                        exit_ts = int(value)

            if start is not None and exit_ts is not None and exit_ts >= start:
                delta = timedelta(microseconds=exit_ts - start)
                total_seconds = int(delta.total_seconds())
                months, days = divmod(delta.days, 30)
                hours, rem = divmod(total_seconds % 86400, 3600)
                minutes, seconds = divmod(rem, 60)
                parts = []
                if months:
                    parts.append(f"{months}mo")
                if days:
                    parts.append(f"{days}d")
                if hours:
                    parts.append(f"{hours}h")
                if minutes:
                    parts.append(f"{minutes}m")
                parts.append(f"{seconds}s")
                return " ".join(parts)
            return "Unknown"
        except CalledProcessError:
            return "Retrieval Error"

    def get_status(self, task: Task) -> str:
        if self.runtime.is_fake:
            task_state = self._require_fake_state().get_task_state(task.name)
            return task_state.get("status", Status.NOT_RUN_YET)
        try:
            output = self.systemd_adapter.show_property(task.service_name, "LoadState")
            if "not-found" in output:
                return Status.MISSING

            output = self.systemd_adapter.is_active(task.service_name)
            if output == "activating":
                return Status.RUNNING

            result_output = self.systemd_adapter.show_property(task.service_name, "Result")
            if "=" in result_output:
                result_value = result_output.split("=")[-1].strip()
                if result_value == "success":
                    output = self.systemd_adapter.show_property(
                        task.service_name, "ExecMainStartTimestamp"
                    )
                    if output.endswith("=") or output == "":
                        return Status.NOT_RUN_YET
                    return Status.SUCCESS
                return Status.FAILURE

            return Status.ERROR
        except CalledProcessError:
            return Status.ERROR

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
            config_path=str(rclone_config_path) if rclone_config_path.exists() else None,
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
        probability = result.get("probability")
        if probability is not None:
            fake_state.append_task_log(task_name, f"Drive health probability: {probability:.4f}")
        else:
            fake_state.append_task_log(
                task_name, "Model unavailable; using sample SMART data only."
            )

        hdsentinel_snapshot = result.get("hdsentinel", {}).get("snapshot")
        if hdsentinel_snapshot and hdsentinel_snapshot.get("available"):
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
        ddns_script = self.runtime.repo_root / "scripts" / "ddns_update.py"

        # Fake mode avoids local systemd, but DDNS itself is still a provider
        # integration that developers need to exercise against real test records.
        try:
            proc = self.command_runner.popen(
                [sys.executable, str(ddns_script)],
                stdout=PIPE,
                stderr=PIPE,
                text=True,
                bufsize=1,
            )
            stdout_output, stderr_output = self._collect_process_output(
                proc, cancel_event, "ddns-update"
            )
            if stdout_output:
                fake_state.append_task_log(task_name, stdout_output)
            if stderr_output:
                fake_state.append_task_log(task_name, stderr_output)

            if cancel_event.is_set():
                raise RuntimeError("Task was cancelled.")

            if proc.returncode != 0:
                raise RuntimeError(f"DDNS update script exited with code {proc.returncode}")
        except (OSError, SubprocessError) as exc:
            fake_state.append_task_log(task_name, f"Subprocess error: {exc!s}")
            raise RuntimeError(f"Failed to run DDNS update script: {exc!s}") from exc

    def _collect_process_output(
        self,
        proc: Any,
        cancel_event: threading.Event,
        thread_name_prefix: str,
    ) -> Tuple[str, str]:
        output_queue = queue.Queue()  # type: queue.Queue[Tuple[str, str]]

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

        stdout_chunks = []  # type: List[str]
        stderr_chunks = []  # type: List[str]
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
        output_queue: Any, stdout_chunks: List[str], stderr_chunks: List[str]
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
