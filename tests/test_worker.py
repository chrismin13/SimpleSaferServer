import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from simple_safer_server.core.builtin_modules import create_builtin_module_registry
from simple_safer_server.core.job_runner import JobRunResult
from simple_safer_server.core.job_state import JobStateStore, format_timestamp
from simple_safer_server.core.module_lifecycle import (
    module_apply_resources,
    ownership_manifest_for_runtime,
)
from simple_safer_server.worker import run


class FakeConfigManager:
    def get_all_config(self):
        return {
            "backup": {"cloud_enabled": "false"},
            "schedule": {"backup_cloud_time": "03:00"},
        }


def apply_module_for_test(runtime, module_slug):
    module = create_builtin_module_registry().module_for_slug(module_slug)
    ownership_manifest_for_runtime(runtime).record_module_resources(
        module.slug,
        module_apply_resources(module),
    )


def state_store(tmp_path, *, applied=True):
    runtime = SimpleNamespace(data_dir=tmp_path)
    if applied:
        apply_module_for_test(runtime, "ddns")
    return JobStateStore(runtime)


def test_worker_once_loads_planned_jobs(capsys, tmp_path):
    with patch("simple_safer_server.worker.create_builtin_job_runner") as runner_factory:
        runner_factory.return_value.run_job.return_value = JobRunResult(
            name="ddns-update",
            exit_code=0,
            message="Job completed successfully.",
        )

        exit_code = run(
            ["--once"],
            state_store=state_store(tmp_path),
            config_manager=FakeConfigManager(),
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "SimpleSaferServer worker loaded 4 planned jobs." in captured.out
    assert "Ran due jobs: ddns-update" in captured.out


def test_worker_run_job_executes_registered_job(capsys, tmp_path):
    with patch("simple_safer_server.worker.create_builtin_job_runner") as runner_factory:
        runner_factory.return_value.run_job.return_value = JobRunResult(
            name="ddns-update",
            exit_code=0,
            message="Job completed successfully.",
        )

        exit_code = run(
            ["--run-job", "ddns-update"],
            state_store=state_store(tmp_path),
            config_manager=FakeConfigManager(),
        )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ddns-update: Job completed successfully." in captured.out
    runner_factory.return_value.run_job.assert_called_once_with("ddns-update")


def test_worker_run_job_rejects_unapplied_module(capsys, tmp_path):
    with patch("simple_safer_server.worker.create_builtin_job_runner") as runner_factory:
        exit_code = run(
            ["--run-job", "ddns-update"],
            state_store=state_store(tmp_path, applied=False),
            config_manager=FakeConfigManager(),
        )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "DDNS must be applied before it can write config." in captured.err
    runner_factory.return_value.run_job.assert_not_called()


def test_worker_once_skips_jobs_that_are_not_due(capsys, tmp_path):
    store = state_store(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        json.dumps(
            {
                "jobs": {
                    "ddns-update": {
                        "status": "Success",
                        "next_run_at": format_timestamp(datetime.now(UTC) + timedelta(hours=1)),
                    }
                }
            }
        )
    )

    with patch("simple_safer_server.worker.create_builtin_job_runner") as runner_factory:
        exit_code = run(["--once"], state_store=store, config_manager=FakeConfigManager())

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "No worker jobs were due." in captured.out
    runner_factory.return_value.run_job.assert_not_called()
