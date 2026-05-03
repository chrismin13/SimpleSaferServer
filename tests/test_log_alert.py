import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


def _load_log_alert_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "log_alert.py"
    spec = importlib.util.spec_from_file_location("simple_safer_server_log_alert", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load log_alert.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_log_alert_uses_monotonic_ids_after_retention_trim(tmp_path, monkeypatch):
    module = _load_log_alert_module()
    monkeypatch.setenv("SSS_CONFIG_DIR", str(tmp_path))
    alerts_path = tmp_path / "alerts.json"
    alerts_path.write_text(
        json.dumps(
            [
                {"id": 998, "title": "old"},
                {"id": 1005, "title": "newer"},
            ]
        )
    )

    assert module.log_alert("Newest", "message")

    alerts = json.loads(alerts_path.read_text())
    assert alerts[-1]["id"] == 1006
    assert alerts[-1]["title"] == "Newest"


def test_log_alert_keeps_current_alerts_when_atomic_replace_fails(tmp_path, monkeypatch):
    module = _load_log_alert_module()
    from simple_safer_server.services import file_persistence

    monkeypatch.setenv("SSS_CONFIG_DIR", str(tmp_path))
    alerts_path = tmp_path / "alerts.json"
    original_alerts = [{"id": 7, "title": "existing"}]
    alerts_path.write_text(json.dumps(original_alerts))

    def fail_replace(source, target):
        raise OSError("replace failed")

    monkeypatch.setattr(file_persistence.os, "replace", fail_replace)

    assert not module.log_alert("Newest", "message")
    assert json.loads(alerts_path.read_text()) == original_alerts
    assert list(tmp_path.glob(".*.tmp")) == []


def test_log_alert_script_and_config_manager_share_alert_store(tmp_path, monkeypatch):
    module = _load_log_alert_module()
    monkeypatch.setenv("SSS_CONFIG_DIR", str(tmp_path))

    from simple_safer_server.services.config_manager import ConfigManager

    runtime = SimpleNamespace(config_dir=tmp_path, default_mount_point="/media/backup")
    manager = ConfigManager(runtime=runtime)

    assert module.log_alert("Script alert", "message")
    assert manager.log_alert("App alert", "message")

    alerts = json.loads((tmp_path / "alerts.json").read_text())
    assert [alert["id"] for alert in alerts] == [1, 2]
    assert [alert["title"] for alert in alerts] == ["Script alert", "App alert"]


def test_log_alert_initialization_does_not_overwrite_concurrent_append(tmp_path):
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "log_alert.py"
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                str(script_path),
                f"Alert {index}",
                "message",
            ],
            env={**os.environ, "SSS_CONFIG_DIR": str(tmp_path)},
        )
        for index in range(5)
    ]

    for process in processes:
        process.wait(timeout=5)

    assert all(process.returncode == 0 for process in processes)
    alerts = json.loads((tmp_path / "alerts.json").read_text())
    assert len(alerts) == 5
    assert sorted(alert["id"] for alert in alerts) == [1, 2, 3, 4, 5]
