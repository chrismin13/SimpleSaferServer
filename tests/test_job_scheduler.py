import json
from contextlib import suppress
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from simple_safer_server.core.builtin_modules import create_builtin_module_registry
from simple_safer_server.core.job_runner import JobRunResult
from simple_safer_server.core.job_scheduler import WorkerScheduler
from simple_safer_server.core.job_state import (
    JobStateStore,
    daily_time_with_offset,
    format_timestamp,
)
from simple_safer_server.core.jobs import JobDefinition, JobRegistry
from simple_safer_server.core.module_lifecycle import (
    ModuleLifecycleError,
    module_apply_resources,
    ownership_manifest_for_runtime,
)


class FakeRunner:
    def __init__(self, exit_code=0):
        self.exit_code = exit_code
        self.ran = []

    def run_job(self, name):
        self.ran.append(name)
        return JobRunResult(name=name, exit_code=self.exit_code, message=f"{name} done")


class FailingRunner:
    def run_job(self, name):
        raise NotImplementedError(f"{name} has no handler")


def make_store(tmp_path):
    return JobStateStore(SimpleNamespace(data_dir=tmp_path))


def apply_module_for_test(runtime, module_slug):
    module = create_builtin_module_registry().module_for_slug(module_slug)
    ownership_manifest_for_runtime(runtime).record_module_resources(
        module.slug,
        module_apply_resources(module),
    )


def scheduled_job():
    return JobDefinition(
        name="ddns-update",
        module_slug="ddns",
        title="DDNS Update",
        description="Update DNS.",
        task_name="DDNS Update",
        interval_seconds=300,
    )


def test_worker_scheduler_records_success_and_next_run(tmp_path):
    job = scheduled_job()
    store = make_store(tmp_path)
    runner = FakeRunner()
    scheduler = WorkerScheduler(JobRegistry((job,)), runner, store)
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    assert scheduler.run_due_jobs(now=now) == ["ddns-update"]

    state = store.job("ddns-update")
    assert runner.ran == ["ddns-update"]
    assert state["status"] == "Success"
    assert state["last_exit_code"] == 0
    assert state["next_run_at"]


def test_worker_scheduler_skips_unapplied_module_jobs(tmp_path):
    job = scheduled_job()
    runner = FakeRunner()
    scheduler = WorkerScheduler(
        JobRegistry((job,)),
        runner,
        make_store(tmp_path),
        module_registry=create_builtin_module_registry(),
    )

    assert scheduler.run_due_jobs(now=datetime(2026, 1, 1, 12, 0, tzinfo=UTC)) == []
    assert scheduler.seconds_until_next_due(now=datetime(2026, 1, 1, 12, 0, tzinfo=UTC)) is None
    assert runner.ran == []


def test_worker_scheduler_rejects_manual_unapplied_module_job(tmp_path):
    job = scheduled_job()
    runner = FakeRunner()
    scheduler = WorkerScheduler(
        JobRegistry((job,)),
        runner,
        make_store(tmp_path),
        module_registry=create_builtin_module_registry(),
    )

    with pytest.raises(ModuleLifecycleError, match="DDNS must be applied"):
        scheduler.run_job(job, now=datetime(2026, 1, 1, 12, 0, tzinfo=UTC))

    assert runner.ran == []


def test_worker_scheduler_runs_applied_module_jobs(tmp_path):
    runtime = SimpleNamespace(data_dir=tmp_path)
    apply_module_for_test(runtime, "ddns")
    job = scheduled_job()
    runner = FakeRunner()
    scheduler = WorkerScheduler(
        JobRegistry((job,)),
        runner,
        JobStateStore(runtime),
        module_registry=create_builtin_module_registry(),
    )

    assert scheduler.run_due_jobs(now=datetime(2026, 1, 1, 12, 0, tzinfo=UTC)) == ["ddns-update"]
    assert runner.ran == ["ddns-update"]


def test_worker_scheduler_skips_job_before_next_run(tmp_path):
    job = scheduled_job()
    store = make_store(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        json.dumps(
            {
                "jobs": {
                    "ddns-update": {
                        "status": "Success",
                        "next_run_at": format_timestamp(
                            datetime(2026, 1, 1, 12, 5, tzinfo=UTC)
                        ),
                    }
                }
            }
        )
    )
    runner = FakeRunner()
    scheduler = WorkerScheduler(JobRegistry((job,)), runner, store)

    assert scheduler.run_due_jobs(now=datetime(2026, 1, 1, 12, 0, tzinfo=UTC)) == []
    assert runner.ran == []


def test_worker_scheduler_reports_wait_until_next_due(tmp_path):
    job = scheduled_job()
    store = make_store(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        json.dumps(
            {
                "jobs": {
                    "ddns-update": {
                        "status": "Success",
                        "next_run_at": format_timestamp(
                            datetime(2026, 1, 1, 12, 5, tzinfo=UTC)
                        ),
                    }
                }
            }
        )
    )
    scheduler = WorkerScheduler(JobRegistry((job,)), FakeRunner(), store)

    assert scheduler.seconds_until_next_due(now=datetime(2026, 1, 1, 12, 3, tzinfo=UTC)) == 120


def test_worker_scheduler_ignores_unscheduled_jobs(tmp_path):
    job = JobDefinition(
        name="manual",
        module_slug="demo",
        title="Manual",
        description="Manual job.",
    )
    scheduler = WorkerScheduler(JobRegistry((job,)), FakeRunner(), make_store(tmp_path))

    assert scheduler.run_due_jobs(now=datetime.now(UTC)) == []
    assert scheduler.seconds_until_next_due(now=datetime.now(UTC)) is None


def test_worker_scheduler_records_failure_when_runner_raises(tmp_path):
    job = scheduled_job()
    store = make_store(tmp_path)
    scheduler = WorkerScheduler(JobRegistry((job,)), FailingRunner(), store)

    with suppress(NotImplementedError):
        scheduler.run_job(job, now=datetime(2026, 1, 1, 12, 0, tzinfo=UTC))

    state = store.job("ddns-update")
    assert state["status"] == "Failure"
    assert state["last_exit_code"] == 1
    assert "no handler" in state["message"]


def test_daily_time_offset_wraps_around_midnight():
    assert daily_time_with_offset("03:00", -2) == "02:58"
    assert daily_time_with_offset("00:01", -4) == "23:57"
