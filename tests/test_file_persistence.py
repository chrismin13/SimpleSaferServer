import json
import os
import subprocess
import sys
from contextlib import suppress

from simple_safer_server.services.file_persistence import (
    atomic_write_json,
    atomic_write_text,
)


def test_atomic_write_text_preserves_original_when_replace_fails(tmp_path, monkeypatch):
    path = tmp_path / "state.txt"
    path.write_text("original")

    def fail_replace(source, target):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)

    with suppress(OSError):
        atomic_write_text(path, "updated")

    assert path.read_text() == "original"
    assert list(tmp_path.glob(".*.tmp")) == []


def test_atomic_write_json_sets_mode(tmp_path):
    path = tmp_path / "state.json"

    atomic_write_json(path, {"ready": True}, mode=0o600)

    assert json.loads(path.read_text()) == {"ready": True}
    assert path.stat().st_mode & 0o777 == 0o600


def test_locked_json_update_serializes_processes(tmp_path):
    path = tmp_path / "counter.json"
    lock_path = tmp_path / "counter.lock"
    worker = """
import sys
import time
from pathlib import Path
from simple_safer_server.services.file_persistence import locked_json_update

path = Path(sys.argv[1])
lock_path = Path(sys.argv[2])

def update(payload):
    time.sleep(0.01)
    payload["count"] = payload.get("count", 0) + 1
    return payload

locked_json_update(path, lock_path, {"count": 0}, update, file_mode=0o644)
"""

    processes = [
        subprocess.Popen([sys.executable, "-c", worker, str(path), str(lock_path)])
        for _ in range(5)
    ]
    for process in processes:
        process.wait(timeout=5)

    assert all(process.returncode == 0 for process in processes)
    assert json.loads(path.read_text()) == {"count": 5}
