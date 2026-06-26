import pytest

from simple_safer_server.core.job_runner import JobRunner, create_builtin_job_runner
from simple_safer_server.core.jobs import create_builtin_job_registry


def test_builtin_job_runner_runs_ddns_job(monkeypatch):
    from simple_safer_server.modules.ddns import runner as ddns_runner

    calls = []
    monkeypatch.setattr(
        ddns_runner,
        "run_privileged_job_action",
        lambda action: calls.append(action) or 0,
    )
    result = create_builtin_job_runner().run_job("ddns-update")

    assert result.exit_code == 0
    assert result.message == "Job completed successfully."
    assert calls == ["ddns.update"]


def test_builtin_job_runner_reports_ddns_failure(monkeypatch):
    from simple_safer_server.modules.ddns import runner as ddns_runner

    monkeypatch.setattr(ddns_runner, "run_privileged_job_action", lambda action: 1)
    result = create_builtin_job_runner().run_job("ddns-update")

    assert result.exit_code == 1
    assert result.message == "Job failed with exit code 1."


def test_builtin_job_runner_uses_privileged_actions_for_root_capable_jobs(monkeypatch):
    action_calls = []

    def record(action):
        action_calls.append(action)
        return 0

    from simple_safer_server.modules.cloud_backup import runner as cloud_backup_runner
    from simple_safer_server.modules.drive_health import runner as drive_health_runner
    from simple_safer_server.modules.storage import runner as storage_runner

    monkeypatch.setattr(cloud_backup_runner, "run_privileged_job_action", record)
    monkeypatch.setattr(drive_health_runner, "run_privileged_job_action", record)
    monkeypatch.setattr(storage_runner, "run_privileged_job_action", record)

    runner = create_builtin_job_runner()

    assert runner.run_job("cloud-backup").exit_code == 0
    assert runner.run_job("drive-health").exit_code == 0
    assert runner.run_job("mount-check").exit_code == 0
    assert action_calls == [
        "cloud-backup.sync",
        "drive-health.scheduled-check",
        "storage.mount-check",
    ]


def test_job_runner_rejects_registered_job_without_handler():
    registry = create_builtin_job_registry()
    runner = JobRunner(registry, handlers={})

    with pytest.raises(NotImplementedError, match="no runner"):
        runner.run_job("ddns-update")
