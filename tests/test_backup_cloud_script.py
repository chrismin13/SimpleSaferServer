import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "backup_cloud.sh"


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(0o755)


def _run_script(
    tmp_path: Path,
    *,
    cloud_enabled: str | None,
    source_name="storage",
    wrong_source=False,
    missing_marker=False,
    missing_helper=False,
):
    storage_path = tmp_path / source_name
    storage_path.mkdir()
    marker_dir = storage_path / ".simple-safer-server"
    marker_dir.mkdir()
    if not missing_marker:
        (marker_dir / "storage.json").write_text('{"storage_id": "test-storage-id"}')
    source_path = storage_path
    if wrong_source:
        source_path = tmp_path / "wrong-source"
        source_path.mkdir()
    data_dir = tmp_path / "data"
    config_path = data_dir / "config" / "config.conf"
    config_path.parent.mkdir(parents=True)
    lines = [
        "[backup]",
        f"mount_point = {source_path}",
        "from_address = server@example.com",
        "email_address = admin@example.com",
        'rclone_dir = remote:/backup="photos"',
        "bandwidth_limit =",
    ]
    if cloud_enabled is not None:
        lines.append(f"cloud_enabled = {cloud_enabled}")
    lines.extend(
        [
            "[storage]",
            "mode = existing_folder",
            f"path = {storage_path}",
            "storage_id = test-storage-id",
            "[system]",
            "server_name = test-server",
        ]
    )
    config_path.write_text("\n".join(lines) + "\n")
    calls_path = tmp_path / "calls.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "msmtp",
        '#!/bin/sh\nprintf "msmtp\\n" >> "$SSS_TEST_CALLS"\ncat >/dev/null\n',
    )
    _write_executable(
        bin_dir / "rclone",
        '#!/bin/sh\nprintf "rclone:%s\\n" "$@" >> "$SSS_TEST_CALLS"\n',
    )
    _write_executable(bin_dir / "journalctl", "#!/bin/sh\necho journal\n")

    # Match a fresh installation: Python helpers under /opt are readable files,
    # without executable bits. Run the real validator and real INI parser.
    validate_script = tmp_path / "validate_storage_source.py"
    if not missing_helper:
        validate_script.write_bytes((REPO / "scripts" / validate_script.name).read_bytes())
        validate_script.chmod(0o644)
    log_alert_script = tmp_path / "log_alert.py"
    log_alert_script.write_text(
        'import os\nfrom pathlib import Path\n'
        'with Path(os.environ["SSS_TEST_CALLS"]).open("a") as handle:\n'
        '    handle.write("log_alert.py\\n")\n'
    )
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env.get('PATH', '')}",
            "PYTHONPATH": str(REPO),
            "SSS_MODE": "fake",
            "SSS_DATA_DIR": str(data_dir),
            "SSS_CONFIG_FILE": str(config_path),
            "SSS_PYTHON_BIN": sys.executable,
            "SSS_VALIDATE_STORAGE_SCRIPT": str(validate_script),
            "SSS_LOG_ALERT_SCRIPT": str(log_alert_script),
            "SSS_TEST_CALLS": str(calls_path),
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


@pytest.mark.parametrize("enabled", [None, "maybe"])
def test_backup_cloud_script_fails_when_cloud_enabled_is_invalid(tmp_path, enabled):
    result, calls = _run_script(tmp_path, cloud_enabled=enabled)
    assert result.returncode == 1
    assert "Cloud Backup Setting Invalid" in result.stdout
    assert "log_alert.py" in calls
    assert "rclone:" not in calls


def test_backup_cloud_script_exits_cleanly_when_cloud_backup_is_disabled(tmp_path):
    result, calls = _run_script(tmp_path, cloud_enabled="false")
    assert result.returncode == 0
    assert "Cloud backup is disabled." in result.stdout
    assert calls == ""


@pytest.mark.parametrize(
    "source_name", ["storage", "storage=photos", 'family "photos"', "photos & videos"]
)
def test_backup_uses_exact_validated_path_with_nonexecutable_helper(tmp_path, source_name):
    result, calls = _run_script(tmp_path, cloud_enabled="true", source_name=source_name)
    assert result.returncode == 0, result.stderr
    assert f"Storage source verified: {tmp_path / source_name}" in result.stdout
    assert calls.splitlines() == [
        "rclone:sync",
        f"rclone:{tmp_path / source_name}",
        'rclone:remote:/backup="photos"',
        "rclone:--create-empty-src-dirs",
        "rclone:-v",
    ]


@pytest.mark.parametrize("failure", ["wrong_source", "missing_marker", "missing_helper"])
def test_backup_never_calls_rclone_when_source_verification_fails(tmp_path, failure):
    result, calls = _run_script(tmp_path, cloud_enabled="true", **{failure: True})
    assert result.returncode == 1
    assert "log_alert.py" in calls
    assert "rclone:" not in calls
    if failure == "wrong_source":
        assert "does not match the configured storage folder" in result.stderr
