from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from simple_safer_server.core.job_runner import JobRunResult
from simple_safer_server.core.jobs import JobDefinition
from simple_safer_server.services.file_persistence import locked_json_update, read_json
from simple_safer_server.services.runtime import get_runtime
from simple_safer_server.services.schedule_time import normalize_ui_schedule_time


def utc_now() -> datetime:
    return datetime.now(UTC)


def format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def daily_time_with_offset(schedule_time: str, offset_minutes: int = 0) -> str:
    """Return HH:MM after applying a day-wrapping minute offset."""
    normalized = normalize_ui_schedule_time(schedule_time)
    hour_text, minute_text = normalized.split(":")
    total_minutes = ((int(hour_text) * 60) + int(minute_text) + offset_minutes) % (24 * 60)
    hour, minute = divmod(total_minutes, 60)
    return f"{hour:02d}:{minute:02d}"


def next_daily_run_after(now: datetime, schedule_time: str, offset_minutes: int = 0) -> datetime:
    """Return the next local-clock run time as a UTC timestamp."""
    normalized = daily_time_with_offset(schedule_time, offset_minutes)
    hour_text, minute_text = normalized.split(":")
    local_now = now.astimezone()
    next_run = local_now.replace(
        hour=int(hour_text),
        minute=int(minute_text),
        second=0,
        microsecond=0,
    )
    if next_run <= local_now:
        next_run += timedelta(days=1)
    return next_run.astimezone(UTC)


class JobStateStore:
    """Stores worker job run state in one SSS-owned JSON file."""

    def __init__(self, runtime: Any | None = None, path: Path | None = None) -> None:
        self.runtime = runtime or get_runtime()
        self.path = path or (self.runtime.data_dir / "job_state.json")
        self.lock_path = self.path.with_suffix(f"{self.path.suffix}.lock")

    def _default(self) -> dict[str, Any]:
        return {"jobs": {}}

    def read(self) -> dict[str, Any]:
        payload = read_json(self.path, self._default())
        if not isinstance(payload, dict):
            return self._default()
        jobs = payload.get("jobs")
        if not isinstance(jobs, dict):
            payload["jobs"] = {}
        return payload

    def job(self, name: str) -> dict[str, Any]:
        state = self.read().get("jobs", {}).get(name, {})
        return state if isinstance(state, dict) else {}

    def record_started(self, job: JobDefinition, started_at: datetime) -> None:
        started_text = format_timestamp(started_at)

        def update(payload: dict[str, Any]) -> dict[str, Any]:
            jobs = payload.setdefault("jobs", {})
            current = jobs.setdefault(job.name, {})
            current.update(
                {
                    "name": job.name,
                    "title": job.title,
                    "task_name": job.task_name,
                    "status": "Running",
                    "started_at": started_text,
                    "message": "Job is running.",
                }
            )
            return payload

        locked_json_update(
            self.path,
            self.lock_path,
            self._default(),
            update,
            file_mode=0o644,
            lock_mode=0o644,
        )

    def record_finished(
        self,
        job: JobDefinition,
        result: JobRunResult,
        *,
        started_at: datetime,
        finished_at: datetime,
        daily_time: str = "",
    ) -> None:
        duration = max(0, int((finished_at - started_at).total_seconds()))
        next_run_at = None
        if job.interval_seconds > 0:
            next_run_at = format_timestamp(finished_at + timedelta(seconds=job.interval_seconds))
        elif job.is_daily_scheduled and daily_time:
            next_run_at = format_timestamp(next_daily_run_after(finished_at, daily_time))

        def update(payload: dict[str, Any]) -> dict[str, Any]:
            jobs = payload.setdefault("jobs", {})
            current = jobs.setdefault(job.name, {})
            current.update(
                {
                    "name": job.name,
                    "title": job.title,
                    "task_name": job.task_name,
                    "status": "Success" if result.exit_code == 0 else "Failure",
                    "started_at": format_timestamp(started_at),
                    "finished_at": format_timestamp(finished_at),
                    "last_run": format_timestamp(started_at),
                    "last_duration_seconds": duration,
                    "last_exit_code": result.exit_code,
                    "message": result.message,
                }
            )
            if next_run_at is not None:
                current["next_run_at"] = next_run_at
                if job.interval_seconds > 0:
                    current["interval_seconds"] = job.interval_seconds
                if job.is_daily_scheduled:
                    current["daily_time"] = daily_time
            return payload

        locked_json_update(
            self.path,
            self.lock_path,
            self._default(),
            update,
            file_mode=0o644,
            lock_mode=0o644,
        )

    def set_next_run(self, job: JobDefinition, next_run_at: datetime, *, daily_time: str = "") -> None:
        def update(payload: dict[str, Any]) -> dict[str, Any]:
            jobs = payload.setdefault("jobs", {})
            current = jobs.setdefault(job.name, {})
            current.update(
                {
                    "name": job.name,
                    "title": job.title,
                    "task_name": job.task_name,
                    "next_run_at": format_timestamp(next_run_at),
                }
            )
            if daily_time:
                current["daily_time"] = daily_time
            return payload

        locked_json_update(
            self.path,
            self.lock_path,
            self._default(),
            update,
            file_mode=0o644,
            lock_mode=0o644,
        )

    def ensure_daily_next_run(self, job: JobDefinition, now: datetime, daily_time: str) -> None:
        if not job.is_daily_scheduled:
            return
        state = self.job(job.name)
        if state.get("status") == "Running":
            return
        next_run_at = parse_timestamp(state.get("next_run_at"))
        if next_run_at and state.get("daily_time") == daily_time:
            return
        self.set_next_run(job, next_daily_run_after(now, daily_time), daily_time=daily_time)

    def is_due(self, job: JobDefinition, now: datetime) -> bool:
        if not job.is_worker_scheduled:
            return False
        state = self.job(job.name)
        if state.get("status") == "Running":
            return False
        next_run_at = parse_timestamp(state.get("next_run_at"))
        return next_run_at is None or now >= next_run_at

    def seconds_until_due(self, job: JobDefinition, now: datetime) -> int | None:
        if not job.is_worker_scheduled:
            return None
        state = self.job(job.name)
        next_run_at = parse_timestamp(state.get("next_run_at"))
        if next_run_at is None:
            return 0
        return max(0, int((next_run_at - now).total_seconds()))

    def task_log(self, job: JobDefinition) -> str:
        state = self.job(job.name)
        if not state:
            return "No worker job runs recorded yet."

        lines = [
            f"Job: {job.title}",
            f"Status: {state.get('status', 'Unknown')}",
            f"Message: {state.get('message', '')}",
            f"Last run: {state.get('last_run', 'Not Run Yet')}",
            f"Duration: {state.get('last_duration_seconds', 0)}s",
        ]
        if state.get("next_run_at"):
            lines.append(f"Next run: {state['next_run_at']}")
        if state.get("last_exit_code") is not None:
            lines.append(f"Exit code: {state['last_exit_code']}")
        return "\n".join(lines)
