import importlib.util
import json
from pathlib import Path


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
