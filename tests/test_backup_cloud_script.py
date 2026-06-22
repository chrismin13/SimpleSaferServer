import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backup_cloud.sh"


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(0o755)


def _write_config(path: Path, storage_path: Path, *, cloud_enabled: str | None) -> None:
    lines = [
        "[backup]",
        f"mount_point = {storage_path}",
        "from_address = server@example.com",
        "email_address = admin@example.com",
        "rclone_dir = remote:/backup",
        "bandwidth_limit =",
    ]
    if cloud_enabled is not None:
        lines.append(f"cloud_enabled = {cloud_enabled}")
    lines.extend(["", "[system]", "server_name = test-server", ""])
    path.write_text("\n".join(lines))


def _run_script(tmp_path: Path, *, cloud_enabled: str | None):
    storage_path = tmp_path / "storage"
    storage_path.mkdir()
    config_path = tmp_path / "config.conf"
    calls_path = tmp_path / "calls.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    _write_config(config_path, storage_path, cloud_enabled=cloud_enabled)
    _write_executable(
        bin_dir / "fake-python",
        f"""#!/bin/sh
echo "python:$*" >> {calls_path}
case "$1" in
  *validate_storage_source.py) exit 0 ;;
  *log_alert.py) exit 0 ;;
esac
exit 0
""",
    )
    _write_executable(
        bin_dir / "msmtp",
        f"""#!/bin/sh
echo "msmtp:$*" >> {calls_path}
cat >/dev/null
exit 0
""",
    )
    _write_executable(
        bin_dir / "rclone",
        f"""#!/bin/sh
echo "rclone:$*" >> {calls_path}
exit 0
""",
    )
    _write_executable(
        bin_dir / "journalctl",
        "#!/bin/sh\necho journal\n",
    )
    validate_script = tmp_path / "validate_storage_source.py"
    validate_script.write_text("# fake\n")
    validate_script.chmod(0o755)
    log_alert_script = tmp_path / "log_alert.py"
    log_alert_script.write_text("# fake\n")
    log_alert_script.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env.get('PATH', '')}",
            "SSS_CONFIG_FILE": str(config_path),
            "SSS_PYTHON_BIN": str(bin_dir / "fake-python"),
            "SSS_VALIDATE_STORAGE_SCRIPT": str(validate_script),
            "SSS_LOG_ALERT_SCRIPT": str(log_alert_script),
        }
    )
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    calls = calls_path.read_text() if calls_path.exists() else ""
    return result, calls


def test_backup_cloud_script_fails_when_cloud_enabled_is_missing(tmp_path):
    result, calls = _run_script(tmp_path, cloud_enabled=None)

    assert result.returncode == 1
    assert "Cloud Backup Setting Invalid" in result.stdout
    assert "log_alert.py" in calls
    assert "rclone:" not in calls


def test_backup_cloud_script_fails_when_cloud_enabled_is_invalid(tmp_path):
    result, calls = _run_script(tmp_path, cloud_enabled="maybe")

    assert result.returncode == 1
    assert "Cloud Backup Setting Invalid" in result.stdout
    assert "log_alert.py" in calls
    assert "rclone:" not in calls


def test_backup_cloud_script_exits_cleanly_when_cloud_backup_is_disabled(tmp_path):
    result, calls = _run_script(tmp_path, cloud_enabled="false")

    assert result.returncode == 0
    assert "Cloud backup is disabled." in result.stdout
    assert calls == ""


def test_backup_cloud_script_runs_validation_and_rclone_when_enabled(tmp_path):
    result, calls = _run_script(tmp_path, cloud_enabled="true")

    assert result.returncode == 0
    assert "validate_storage_source.py" in calls
    assert "rclone:sync" in calls
