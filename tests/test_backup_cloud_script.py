import json
import os
import shutil
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
    relative_overrides=False,
    environment=None,
    destination='remote:/backup="photos"',
    rclone_executable=None,
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
        f"rclone_dir = {destination}",
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
    if rclone_executable:
        (bin_dir / 'rclone').symlink_to(rclone_executable)
    else:
        _write_executable(
            bin_dir / "rclone",
            f'#!{sys.executable}\n'
            'import json, os, sys\nfrom pathlib import Path\n'
            'with Path(os.environ["SSS_TEST_CALLS"]).open("a") as handle:\n'
            '    handle.write("rclone-cwd:" + os.getcwd() + "\\n")\n'
            '    handle.writelines("rclone:" + value + "\\n" for value in sys.argv[1:])\n'
            'if "SSS_TEST_ENV_OUTPUT" in os.environ:\n'
            '    Path(os.environ["SSS_TEST_ENV_OUTPUT"]).write_text(json.dumps({\n'
            '        "rclone_names": [name for name in os.environ if name.startswith("RCLONE_")],\n'
            '        "preserved": os.environ.get("SSS_TEST_PRESERVED"),\n'
            '        "provider_profile": os.environ.get("AWS_PROFILE"),\n'
            '        "path": os.environ.get("PATH"),\n'
            '    }))\n',
        )
    _write_executable(bin_dir / "journalctl", "#!/bin/sh\necho journal\n")

    # Match a fresh installation: Python helpers under /opt are readable files,
    # without executable bits. Run the real validator and real INI parser.
    # Give the copied helper an app layout so it imports this checkout, even
    # when a separate installed SSS exists at /opt/SimpleSaferServer.
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'simple_safer_server').symlink_to(REPO / 'simple_safer_server')
    validate_script = tmp_path / 'scripts' / 'validate_storage_source.py'
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
            "SSS_RCLONE_CONFIG_FILE": str(data_dir / "rclone" / "rclone.conf"),
            "SSS_PYTHON_BIN": sys.executable,
            "SSS_VALIDATE_STORAGE_SCRIPT": str(validate_script),
            "SSS_LOG_ALERT_SCRIPT": str(log_alert_script),
            "SSS_TEST_CALLS": str(calls_path),
        }
    )
    if relative_overrides:
        env['PATH'] = f"bin:{os.environ.get('PATH', '')}"
        for key in (
            'SSS_CONFIG_FILE',
            'SSS_RCLONE_CONFIG_FILE',
            'SSS_PYTHON_BIN',
            'SSS_VALIDATE_STORAGE_SCRIPT',
            'SSS_LOG_ALERT_SCRIPT',
        ):
            env[key] = os.path.relpath(env[key], tmp_path)
    env.update(environment or {})
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        cwd=tmp_path,
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
    "source_name",
    ["storage", "storage=photos", 'family "photos"', "photos & videos", "100% photos"],
)
def test_backup_uses_exact_validated_path_with_nonexecutable_helper(tmp_path, source_name):
    result, calls = _run_script(tmp_path, cloud_enabled="true", source_name=source_name)
    assert result.returncode == 0, result.stderr
    assert f"Storage source verified: {tmp_path / source_name}" in result.stdout
    assert calls.splitlines() == [
        "rclone-cwd:/",
        "rclone:sync",
        f"rclone:{tmp_path / source_name}",
        'rclone:remote:/backup="photos"',
        "rclone:--config",
        f"rclone:{tmp_path / 'data' / 'rclone' / 'rclone.conf'}",
        "rclone:--create-empty-src-dirs",
        "rclone:-v",
    ]


def test_backup_resolves_relative_overrides_before_changing_rclone_directory(tmp_path):
    result, calls = _run_script(tmp_path, cloud_enabled='true', relative_overrides=True)
    assert result.returncode == 0, result.stderr
    assert 'rclone-cwd:/\n' in calls
    assert f"rclone:{tmp_path / 'data' / 'rclone' / 'rclone.conf'}\n" in calls
    assert f"Storage source verified: {tmp_path / 'storage'}" in result.stdout


def test_backup_filters_rclone_overrides_and_preserves_unrelated_environment(tmp_path):
    output = tmp_path / 'rclone-environment.json'
    result, calls = _run_script(
        tmp_path,
        cloud_enabled='true',
        environment={
            'SSS_TEST_ENV_OUTPUT': str(output),
            'SSS_TEST_PRESERVED': 'value with spaces\nand a newline',
            'AWS_PROFILE': 'managed-provider-profile',
            'RCLONE_CONFIG_REMOTE_REMOTE': '/unconfirmed-destination',
            # Bash cannot address these as shell variables, but rclone can read
            # them from its environment for remote names containing punctuation.
            'RCLONE_CONFIG_SAVED-CLOUD_REMOTE': '/other-destination',
            'RCLONE_CONFIG': '/other/rclone.conf',
            'RCLONE_S3_SECRET_ACCESS_KEY': 'ambient-credential\nsecond line',
            'RCLONE_RC_PASS': 'ambient-password',
        },
    )
    assert result.returncode == 0, result.stderr
    environment = json.loads(output.read_text())
    assert environment['rclone_names'] == []
    assert environment['preserved'] == 'value with spaces\nand a newline'
    assert environment['provider_profile'] == 'managed-provider-profile'
    assert environment['path'] == f"{tmp_path / 'bin'}:{os.environ.get('PATH', '')}"
    assert 'ambient-credential' not in calls + result.stdout + result.stderr
    assert 'ambient-password' not in calls + result.stdout + result.stderr


@pytest.mark.skipif(not shutil.which('rclone'), reason='Requires installed rclone')
def test_production_backup_syncs_managed_destination_despite_environment_override(tmp_path):
    chosen = tmp_path / 'chosen'
    overridden = tmp_path / 'overridden'
    for destination in (chosen, overridden):
        (destination / 'Backups').mkdir(parents=True)
        (destination / 'Backups' / 'existing.txt').write_text('existing data')
    config_path = tmp_path / 'data' / 'rclone' / 'rclone.conf'
    config_path.parent.mkdir(parents=True)
    config_path.write_text(f'[remote]\ntype = alias\nremote = {chosen}\n')
    result, _ = _run_script(
        tmp_path,
        cloud_enabled='true',
        destination='remote:Backups',
        rclone_executable=shutil.which('rclone'),
        environment={'RCLONE_CONFIG_REMOTE_REMOTE': str(overridden)},
    )
    assert result.returncode == 0, result.stderr
    assert (chosen / 'Backups' / '.simple-safer-server' / 'storage.json').exists()
    assert not (chosen / 'Backups' / 'existing.txt').exists()
    assert [path.name for path in (overridden / 'Backups').iterdir()] == ['existing.txt']
    assert (overridden / 'Backups' / 'existing.txt').read_text() == 'existing data'


@pytest.mark.parametrize("failure", ["wrong_source", "missing_marker", "missing_helper"])
def test_backup_never_calls_rclone_when_source_verification_fails(tmp_path, failure):
    result, calls = _run_script(tmp_path, cloud_enabled="true", **{failure: True})
    assert result.returncode == 1
    assert "log_alert.py" in calls
    assert "rclone:" not in calls
    if failure == "wrong_source":
        assert "does not match the configured storage folder" in result.stderr
