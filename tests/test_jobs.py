import pytest

from simple_safer_server.core.builtin_modules import create_builtin_module_registry
from simple_safer_server.core.jobs import JobDefinition, JobRegistry, create_builtin_job_registry


def test_builtin_job_registry_lists_worker_jobs():
    registry = create_builtin_job_registry()

    assert [job.name for job in registry.list_jobs()] == [
        "cloud-backup",
        "ddns-update",
        "drive-health",
        "mount-check",
    ]
    cloud_backup = registry.job_for_name("cloud-backup")
    assert cloud_backup.is_worker_scheduled
    assert cloud_backup.is_daily_scheduled
    assert cloud_backup.default_daily_time == "03:00"
    assert registry.job_for_name("ddns-update").interval_seconds == 300
    assert registry.job_for_name("ddns-update").is_worker_scheduled
    drive_health = registry.job_for_name("drive-health")
    assert drive_health.is_worker_scheduled
    assert drive_health.daily_time_offset_minutes == -2
    mount_check = registry.job_for_name("mount-check")
    assert mount_check.is_worker_scheduled
    assert mount_check.daily_time_offset_minutes == -4


def test_builtin_job_registry_collects_jobs_from_module_contracts():
    registry = create_builtin_job_registry()
    module_jobs = sorted(
        job.name
        for module in create_builtin_module_registry().list_modules()
        for job in module.jobs
    )

    assert [job.name for job in registry.list_jobs()] == module_jobs


def test_job_registry_rejects_duplicate_names():
    job = JobDefinition(
        name="duplicate",
        module_slug="demo",
        title="Duplicate",
        description="Duplicate job.",
    )

    with pytest.raises(ValueError, match="unique"):
        JobRegistry((job, job))
