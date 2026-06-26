from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JobDefinition:
    name: str
    module_slug: str
    title: str
    description: str
    task_name: str = ""
    interval_seconds: int = 0
    daily_time_config_section: str = ""
    daily_time_config_key: str = ""
    default_daily_time: str = ""
    daily_time_offset_minutes: int = 0
    enabled_config_section: str = ""
    enabled_config_key: str = ""
    enabled_config_value: str = "true"

    @property
    def is_worker_scheduled(self) -> bool:
        return self.interval_seconds > 0 or bool(self.daily_time_config_key)

    @property
    def is_daily_scheduled(self) -> bool:
        return bool(self.daily_time_config_key)

    def is_enabled(self, config: dict | None = None) -> bool:
        if not self.enabled_config_key:
            return True
        config = config or {}
        section = config.get(self.enabled_config_section, {})
        value = section.get(self.enabled_config_key, "")
        return str(value).strip().lower() == self.enabled_config_value.lower()

    def daily_time_from_config(self, config: dict | None = None) -> str:
        if not self.daily_time_config_key:
            return ""
        config = config or {}
        section = config.get(self.daily_time_config_section, {})
        return str(section.get(self.daily_time_config_key, self.default_daily_time))


class JobRegistry:
    def __init__(self, jobs: tuple[JobDefinition, ...]):
        names = [job.name for job in jobs]
        if len(names) != len(set(names)):
            raise ValueError("Job names must be unique.")
        self._jobs = tuple(sorted(jobs, key=lambda job: job.name))

    def list_jobs(self) -> tuple[JobDefinition, ...]:
        return self._jobs

    def job_for_name(self, name: str) -> JobDefinition:
        for job in self._jobs:
            if job.name == name:
                return job
        raise KeyError(name)


def create_builtin_job_registry() -> JobRegistry:
    """List background jobs owned by the SimpleSaferServer worker."""
    from simple_safer_server.core.builtin_modules import create_builtin_module_registry

    jobs = tuple(
        job
        for module in create_builtin_module_registry().list_modules()
        for job in module.jobs
    )
    return JobRegistry(jobs)
