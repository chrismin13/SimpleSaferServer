import os
import subprocess
import textwrap
from pathlib import Path


def write_executable(path: Path, text: str) -> None:
    path.write_text(textwrap.dedent(text))
    path.chmod(0o755)


def make_backup_config(path: Path, *, healthchecks_url: str = "") -> None:
    path.write_text(
        textwrap.dedent(
            f"""\
            [backup]
            mount_point = /
            from_address = alerts@example.test
            email_address = admin@example.test
            rclone_dir = remote:/backup
            bandwidth_limit =
            healthchecks_ping_url = {healthchecks_url}

            [system]
            server_name = test-server
            """
        )
    )


def run_backup_script(tmp_path: Path, *, rclone_exit: int, healthchecks_url: str):
    fake_bin = tmp_path / "bin"
    fake_scripts = tmp_path / "scripts"
    fake_bin.mkdir()
    fake_scripts.mkdir()
    config_path = tmp_path / "config.conf"
    make_backup_config(config_path, healthchecks_url=healthchecks_url)

    write_executable(
        fake_bin / "rclone",
        """\
        #!/bin/sh
        printf '%s\\n' "$*" > "$RCLONE_ARGS_FILE"
        exit "$RCLONE_EXIT"
        """,
    )
    write_executable(
        fake_bin / "msmtp",
        """\
        #!/bin/sh
        cat >/dev/null
        exit 0
        """,
    )
    write_executable(
        fake_bin / "journalctl",
        """\
        #!/bin/sh
        printf '%s\\n' 'recent backup logs'
        exit 0
        """,
    )
    write_executable(
        tmp_path / "python",
        """\
        #!/bin/sh
        case "$1" in
          */ping_healthchecks.py)
            printf '%s\\n' "$*" > "$PY_ARGS_FILE"
            cat > "$PING_STDIN_FILE"
            exit "${PING_EXIT:-0}"
            ;;
          *)
            printf '%s\\n' "$*" > "$LOG_ALERT_ARGS_FILE"
            exit 0
            ;;
        esac
        """,
    )

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "SSS_CONFIG_FILE": str(config_path),
            "SSS_PYTHON_BIN": str(tmp_path / "python"),
            "SSS_SCRIPTS_DIR": str(fake_scripts),
            "RCLONE_EXIT": str(rclone_exit),
            "RCLONE_ARGS_FILE": str(tmp_path / "rclone.args"),
            "PY_ARGS_FILE": str(tmp_path / "python.args"),
            "PING_STDIN_FILE": str(tmp_path / "ping.stdin"),
            "LOG_ALERT_ARGS_FILE": str(tmp_path / "log-alert.args"),
        }
    )

    return subprocess.run(
        ["bash", "scripts/backup_cloud.sh"],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def test_backup_cloud_script_pings_healthchecks_after_success_without_argv_leak(tmp_path):
    result = run_backup_script(
        tmp_path,
        rclone_exit=0,
        healthchecks_url="https://hc-ping.com/secret-check-id",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (tmp_path / "ping.stdin").read_text() == "https://hc-ping.com/secret-check-id"
    assert "ping_healthchecks.py" in (tmp_path / "python.args").read_text()
    assert "secret-check-id" not in (tmp_path / "python.args").read_text()
    assert "secret-check-id" not in (tmp_path / "rclone.args").read_text()
    assert "secret-check-id" not in result.stdout
    assert "secret-check-id" not in result.stderr


def test_backup_cloud_script_does_not_ping_healthchecks_after_rclone_failure(tmp_path):
    result = run_backup_script(
        tmp_path,
        rclone_exit=1,
        healthchecks_url="https://hc-ping.com/secret-check-id",
    )

    assert result.returncode == 1
    assert not (tmp_path / "ping.stdin").exists()
    assert not (tmp_path / "python.args").exists()
    assert (tmp_path / "log-alert.args").exists()
