from __future__ import annotations

from typing import Any

from simple_safer_server.core.jobs import JobDefinition
from simple_safer_server.core.module_contract import ModuleRegistry
from simple_safer_server.core.module_lifecycle import (
    ModuleLifecycleError,
    module_is_applied,
    require_module_applied,
)


def module_for_job(job: JobDefinition, module_registry: ModuleRegistry):
    try:
        return module_registry.module_for_slug(job.module_slug)
    except KeyError as exc:
        raise ModuleLifecycleError(
            f"{job.title} belongs to unknown module: {job.module_slug}."
        ) from exc


def job_module_is_applied(
    job: JobDefinition,
    *,
    module_registry: ModuleRegistry | None,
    runtime: Any,
) -> bool:
    """Return whether the job's owning module has completed setup."""
    if module_registry is None:
        return True
    return module_is_applied(module_for_job(job, module_registry), runtime)


def require_job_module_applied(
    job: JobDefinition,
    *,
    module_registry: ModuleRegistry | None,
    runtime: Any,
) -> None:
    """Block module-owned jobs until the setup flow has recorded ownership."""
    if module_registry is None:
        return
    require_module_applied(module_for_job(job, module_registry), runtime)
