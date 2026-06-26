from __future__ import annotations

from datetime import datetime

from simple_safer_server.core.job_lifecycle import (
    job_module_is_applied,
    require_job_module_applied,
)
from simple_safer_server.core.job_runner import JobRunner, JobRunResult
from simple_safer_server.core.job_state import JobStateStore, daily_time_with_offset, utc_now
from simple_safer_server.core.jobs import JobDefinition, JobRegistry
from simple_safer_server.core.module_contract import ModuleRegistry


class WorkerScheduler:
    """Runs due worker-managed jobs and records their last result."""

    def __init__(
        self,
        registry: JobRegistry,
        runner: JobRunner,
        state_store: JobStateStore,
        config_manager=None,
        module_registry: ModuleRegistry | None = None,
    ) -> None:
        self.registry = registry
        self.runner = runner
        self.state_store = state_store
        self.config_manager = config_manager
        self.module_registry = module_registry

    def _config(self) -> dict:
        if self.config_manager is None:
            return {}
        return self.config_manager.get_all_config()

    def _daily_time(self, job: JobDefinition) -> str:
        if not job.is_daily_scheduled:
            return ""
        return daily_time_with_offset(
            job.daily_time_from_config(self._config()),
            job.daily_time_offset_minutes,
        )

    def _is_job_enabled(self, job: JobDefinition) -> bool:
        return job.is_enabled(self._config())

    def _is_job_module_applied(self, job: JobDefinition) -> bool:
        return job_module_is_applied(
            job,
            module_registry=self.module_registry,
            runtime=self.state_store.runtime,
        )

    def _require_job_module_applied(self, job: JobDefinition) -> None:
        require_job_module_applied(
            job,
            module_registry=self.module_registry,
            runtime=self.state_store.runtime,
        )

    def _prepare_schedule(self, job: JobDefinition, now: datetime) -> None:
        if (
            job.is_daily_scheduled
            and self._is_job_enabled(job)
            and self._is_job_module_applied(job)
        ):
            self.state_store.ensure_daily_next_run(job, now, self._daily_time(job))

    def scheduled_jobs(self) -> tuple[JobDefinition, ...]:
        return tuple(job for job in self.registry.list_jobs() if job.is_worker_scheduled)

    def run_job(self, job: JobDefinition, *, now: datetime | None = None):
        self._require_job_module_applied(job)
        started_at = now or utc_now()
        daily_time = self._daily_time(job)
        self.state_store.record_started(job, started_at)
        try:
            result = self.runner.run_job(job.name)
        except Exception as exc:
            result = JobRunResult(
                name=job.name,
                exit_code=1,
                message=f"Job failed: {exc}",
            )
            self.state_store.record_finished(
                job,
                result,
                started_at=started_at,
                finished_at=utc_now(),
                daily_time=daily_time,
            )
            raise
        self.state_store.record_finished(
            job,
            result,
            started_at=started_at,
            finished_at=utc_now(),
            daily_time=daily_time,
        )
        return result

    def run_due_jobs(self, *, now: datetime | None = None) -> list[str]:
        now = now or utc_now()
        ran: list[str] = []
        for job in self.scheduled_jobs():
            if not self._is_job_enabled(job) or not self._is_job_module_applied(job):
                continue
            self._prepare_schedule(job, now)
            if self.state_store.is_due(job, now):
                self.run_job(job, now=now)
                ran.append(job.name)
        return ran

    def seconds_until_next_due(self, *, now: datetime | None = None) -> int | None:
        now = now or utc_now()
        for job in self.scheduled_jobs():
            self._prepare_schedule(job, now)
        waits = [
            wait
            for job in self.scheduled_jobs()
            if self._is_job_enabled(job)
            and self._is_job_module_applied(job)
            and (wait := self.state_store.seconds_until_due(job, now)) is not None
        ]
        if not waits:
            return None
        return min(waits)
