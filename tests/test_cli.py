import json
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from simple_safer_server.cli import run
from simple_safer_server.core.builtin_modules import create_builtin_module_registry
from simple_safer_server.core.job_runner import JobRunResult
from simple_safer_server.core.module_lifecycle import (
    module_apply_resources,
    ownership_manifest_for_runtime,
)


def run_cli(args):
    stdout = StringIO()
    stderr = StringIO()
    exit_code = run(args, stdout=stdout, stderr=stderr)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def apply_module_for_test(runtime, module_slug):
    module = create_builtin_module_registry().module_for_slug(module_slug)
    ownership_manifest_for_runtime(runtime).record_module_resources(
        module.slug,
        module_apply_resources(module),
    )


class FakeConfigManager:
    def get_all_config(self):
        return {
            "backup": {"cloud_enabled": "false"},
            "schedule": {"backup_cloud_time": "03:00"},
        }


def test_status_reports_registered_modules():
    exit_code, stdout, stderr = run_cli(["status"])

    assert exit_code == 0
    assert stderr == ""
    assert "SimpleSaferServer CLI is available." in stdout
    assert "Registered modules: 7" in stdout
    assert "Registered worker jobs: 4" in stdout
    assert "Worker service: simple-safer-server-worker.service" in stdout


def test_doctor_reports_runtime_and_module_tool_visibility(tmp_path):
    runtime = SimpleNamespace(
        mode="fake",
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        logs_dir=tmp_path / "logs",
    )

    with (
        patch("simple_safer_server.cli.get_runtime", return_value=runtime),
        patch("simple_safer_server.core.module_checks.shutil.which", return_value=None),
    ):
        exit_code, stdout, stderr = run_cli(["doctor"])

    assert exit_code == 0
    assert stderr == ""
    assert "SimpleSaferServer doctor" in stdout
    assert f"- app data: {runtime.data_dir}" in stdout
    assert "- privileged actions: 20" in stdout
    assert "alerts: update-ca-certificates missing" in stdout
    assert "cloud-backup: rclone missing" in stdout
    assert "ddns: update-ca-certificates missing" in stdout
    assert "file-sharing: smbd missing" in stdout
    assert "file-sharing: nmbd missing (optional)" in stdout


def test_module_list_shows_builtin_modules(tmp_path):
    runtime = SimpleNamespace(data_dir=tmp_path)

    with patch("simple_safer_server.cli.get_runtime", return_value=runtime):
        exit_code, stdout, stderr = run_cli(["module", "list"])

    assert exit_code == 0
    assert stderr == ""
    assert "Applied" in stdout
    assert "cloud-backup" in stdout
    assert "file-sharing" in stdout
    assert "system-updates" in stdout


def test_module_list_marks_applied_modules(tmp_path):
    runtime = SimpleNamespace(data_dir=tmp_path)
    apply_module_for_test(runtime, "alerts")

    with patch("simple_safer_server.cli.get_runtime", return_value=runtime):
        exit_code, stdout, stderr = run_cli(["module", "list"])

    assert exit_code == 0
    assert stderr == ""
    alerts_line = next(line for line in stdout.splitlines() if line.startswith("alerts"))
    assert alerts_line.split()[:3] == ["alerts", "active", "yes"]


def test_module_plan_shows_ownership_and_privileged_actions():
    with patch("simple_safer_server.core.module_checks.shutil.which", return_value=None):
        exit_code, stdout, stderr = run_cli(["module", "plan", "cloud-backup"])

    assert exit_code == 0
    assert stderr == ""
    assert "Module: cloud-backup" in stdout
    assert "rclone [missing]" in stdout
    assert "/etc/SimpleSaferServer/rclone/rclone.conf" in stdout
    assert "cloud-backup.write-rclone-config" in stdout
    assert "cloud-backup.sync" in stdout


def test_module_plan_marks_resources_recorded_after_specific_writes():
    exit_code, stdout, stderr = run_cli(["module", "plan", "storage"])

    assert exit_code == 0
    assert stderr == ""
    assert "/etc/fstab#SimpleSaferServer managed backup drive" in stdout
    assert "recorded after specific write" in stdout


def test_module_check_reports_required_tool_status():
    with patch(
        "simple_safer_server.core.module_checks.shutil.which",
        return_value="/usr/bin/rclone",
    ):
        exit_code, stdout, stderr = run_cli(["module", "check", "cloud-backup"])

    assert exit_code == 0
    assert stderr == ""
    assert "Module: cloud-backup" in stdout
    assert "Required tools are available." in stdout
    assert "rclone: available at /usr/bin/rclone" in stdout


def test_module_plan_rejects_unknown_slug():
    exit_code, stdout, stderr = run_cli(["module", "plan", "missing"])

    assert exit_code == 2
    assert stdout == ""
    assert "Unknown module: missing" in stderr


def test_module_apply_records_owned_resources(tmp_path):
    runtime = SimpleNamespace(data_dir=tmp_path)

    with (
        patch("simple_safer_server.cli.get_runtime", return_value=runtime),
        patch(
            "simple_safer_server.core.module_checks.shutil.which",
            return_value="/usr/sbin/update-ca-certificates",
        ),
    ):
        exit_code, stdout, stderr = run_cli(["module", "apply", "alerts"])

    assert exit_code == 0
    assert stderr == ""
    assert "Recorded ownership for module: alerts" in stdout
    assert "<config>/smtp.conf" in stdout
    assert (tmp_path / "ownership.json").exists()


def test_module_uninstall_removes_app_owned_files_and_records(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    smtp_config = config_dir / "smtp.conf"
    smtp_config.write_text("smtp", encoding="utf-8")
    runtime = SimpleNamespace(data_dir=tmp_path, config_dir=config_dir)

    with (
        patch("simple_safer_server.cli.get_runtime", return_value=runtime),
        patch(
            "simple_safer_server.core.module_checks.shutil.which",
            return_value="/usr/sbin/update-ca-certificates",
        ),
    ):
        apply_exit, _apply_stdout, apply_stderr = run_cli(["module", "apply", "alerts"])
        uninstall_exit, stdout, stderr = run_cli(["module", "uninstall", "alerts"])

    assert apply_exit == 0
    assert apply_stderr == ""
    assert uninstall_exit == 0
    assert stderr == ""
    assert "Removed ownership records for module: alerts" in stdout
    assert "Module uninstall removed only records that were safe for generic cleanup" in stdout
    assert str(smtp_config) in stdout
    assert not smtp_config.exists()


def test_module_apply_rejects_unknown_slug():
    exit_code, stdout, stderr = run_cli(["module", "apply", "missing"])

    assert exit_code == 2
    assert stdout == ""
    assert "Unknown module: missing" in stderr


def test_module_apply_rejects_read_only_module(tmp_path):
    runtime = SimpleNamespace(data_dir=tmp_path)

    with patch("simple_safer_server.cli.get_runtime", return_value=runtime):
        exit_code, stdout, stderr = run_cli(["module", "apply", "system-updates"])

    assert exit_code == 2
    assert stdout == ""
    assert "System Updates is read-only" in stderr


def test_module_apply_blocks_missing_required_tools(tmp_path):
    runtime = SimpleNamespace(data_dir=tmp_path)

    with (
        patch("simple_safer_server.cli.get_runtime", return_value=runtime),
        patch("simple_safer_server.core.module_checks.shutil.which", return_value=None),
    ):
        exit_code, stdout, stderr = run_cli(["module", "apply", "cloud-backup"])

    assert exit_code == 2
    assert stdout == ""
    assert "required tools are missing: update-ca-certificates, rclone" in stderr
    assert not (tmp_path / "ownership.json").exists()


def test_job_list_shows_worker_transition_targets():
    exit_code, stdout, stderr = run_cli(["job", "list"])

    assert exit_code == 0
    assert stderr == ""
    assert "cloud-backup" in stdout
    assert "worker daily 03:00" in stdout
    assert "ddns-update" in stdout
    assert "worker every 300s" in stdout
    assert "drive-health" in stdout
    assert "worker daily 03:00 -2m" in stdout
    assert "mount-check" in stdout
    assert "worker daily 03:00 -4m" in stdout


def test_job_run_rejects_unknown_job():
    exit_code, stdout, stderr = run_cli(["job", "run", "missing"])

    assert exit_code == 2
    assert stdout == ""
    assert "Unknown job: missing" in stderr


def test_job_run_rejects_unapplied_module_job(tmp_path):
    runtime = SimpleNamespace(data_dir=tmp_path)
    with (
        patch("simple_safer_server.cli.get_runtime", return_value=runtime),
        patch("simple_safer_server.cli.ConfigManager", return_value=FakeConfigManager()),
        patch("simple_safer_server.cli.create_builtin_job_runner") as runner_factory,
    ):
        exit_code, stdout, stderr = run_cli(["job", "run", "ddns-update"])

    assert exit_code == 2
    assert stdout == ""
    assert "DDNS must be applied before it can write config." in stderr
    runner_factory.return_value.run_job.assert_not_called()


def test_job_run_executes_registered_job_and_records_state(tmp_path):
    runtime = SimpleNamespace(data_dir=tmp_path)
    apply_module_for_test(runtime, "ddns")
    with (
        patch("simple_safer_server.cli.get_runtime", return_value=runtime),
        patch("simple_safer_server.cli.ConfigManager", return_value=FakeConfigManager()),
        patch("simple_safer_server.cli.create_builtin_job_runner") as runner_factory,
    ):
        runner_factory.return_value.run_job.return_value = JobRunResult(
            name="ddns-update",
            exit_code=0,
            message="Job completed successfully.",
        )

        exit_code, stdout, stderr = run_cli(["job", "run", "ddns-update"])

    assert exit_code == 0
    assert stderr == ""
    assert "ddns-update: Job completed successfully." in stdout
    runner_factory.return_value.run_job.assert_called_once_with("ddns-update")
    state = json.loads((tmp_path / "job_state.json").read_text(encoding="utf-8"))
    assert state["jobs"]["ddns-update"]["status"] == "Success"
    assert state["jobs"]["ddns-update"]["last_exit_code"] == 0


def test_alert_send_uses_alert_notifier():
    runtime = SimpleNamespace(is_fake=True)
    with (
        patch("simple_safer_server.cli.get_runtime", return_value=runtime),
        patch("simple_safer_server.cli.ConfigManager") as config_manager_class,
        patch("simple_safer_server.cli.AlertNotifier") as notifier_class,
    ):
        exit_code, stdout, stderr = run_cli(
            [
                "alert",
                "send",
                "Backup failed",
                "message",
                "--type",
                "error",
                "--source",
                "backup_cloud",
            ]
        )

    assert exit_code == 0
    assert stderr == ""
    config_manager_class.assert_called_once_with(runtime=runtime)
    notifier_class.return_value.notify.assert_called_once_with(
        "Backup failed",
        "message",
        alert_type="error",
        source="backup_cloud",
    )
    assert "Alert sent: Backup failed" in stdout
