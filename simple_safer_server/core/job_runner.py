from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from simple_safer_server.core.jobs import JobRegistry, create_builtin_job_registry

JobHandler = Callable[[], int | None]


@dataclass(frozen=True)
class JobRunResult:
    name: str
    exit_code: int
    message: str


class JobRunner:
    """Dispatches module-owned jobs from the CLI, worker, and future scheduler."""

    def __init__(self, registry: JobRegistry, handlers: dict[str, JobHandler]):
        self._registry = registry
        self._handlers = dict(handlers)

    def run_job(self, name: str) -> JobRunResult:
        self._registry.job_for_name(name)
        handler = self._handlers.get(name)
        if handler is None:
            raise NotImplementedError(f"Job is registered but has no runner yet: {name}")

        try:
            exit_code = int(handler() or 0)
        except Exception as exc:
            return JobRunResult(name=name, exit_code=1, message=f"Job failed: {exc}")

        if exit_code == 0:
            message = "Job completed successfully."
        else:
            message = f"Job failed with exit code {exit_code}."
        return JobRunResult(name=name, exit_code=exit_code, message=message)


def create_builtin_job_runner(registry: JobRegistry | None = None) -> JobRunner:
    from simple_safer_server.modules.cloud_backup.runner import run_backup_job
    from simple_safer_server.modules.ddns.runner import run_update_job
    from simple_safer_server.modules.drive_health.runner import run_drive_health_job
    from simple_safer_server.modules.storage.runner import run_mount_check_job

    registry = registry or create_builtin_job_registry()
    return JobRunner(
        registry,
        handlers={
            "cloud-backup": run_backup_job,
            "ddns-update": run_update_job,
            "drive-health": run_drive_health_job,
            "mount-check": run_mount_check_job,
        },
    )
