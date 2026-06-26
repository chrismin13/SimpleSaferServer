from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from simple_safer_server.core.privileged_client import (
    PrivilegedActionClient,
    PrivilegedActionClientError,
    default_helper_command,
)


class FakeCommandRunner:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return self.result


def test_privileged_action_client_sends_json_on_stdin():
    runner = FakeCommandRunner(
        SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "action": "file-sharing.reload",
                    "data": {"message": "File sharing services reloaded."},
                }
            ),
            stderr="",
        )
    )
    client = PrivilegedActionClient(
        command_runner=runner,
        helper_command=("sss-helper",),
        timeout=12,
    )

    result = client.run("file-sharing.reload", {})

    assert result.data == {"message": "File sharing services reloaded."}
    command, kwargs = runner.calls[0]
    assert command == ["sss-helper", "run", "file-sharing.reload"]
    assert kwargs["input"] == "{}"
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["timeout"] == 12


def test_privileged_action_client_reports_helper_rejection():
    runner = FakeCommandRunner(
        SimpleNamespace(
            returncode=2,
            stdout="",
            stderr="Missing required privileged action payload field: partition\n",
        )
    )
    client = PrivilegedActionClient(command_runner=runner, helper_command=("sss-helper",))

    with pytest.raises(PrivilegedActionClientError, match="Missing required") as exc_info:
        client.run("storage.managed-drive", {})

    assert exc_info.value.exit_code == 2


def test_privileged_action_client_rejects_invalid_helper_json():
    runner = FakeCommandRunner(SimpleNamespace(returncode=0, stdout="not json", stderr=""))
    client = PrivilegedActionClient(command_runner=runner, helper_command=("sss-helper",))

    with pytest.raises(PrivilegedActionClientError, match="invalid JSON"):
        client.run("ddns.update", {})


def test_default_helper_command_uses_sudo_for_installed_non_root(monkeypatch):
    monkeypatch.delenv("SSS_HELPER_COMMAND", raising=False)
    monkeypatch.setattr(
        "simple_safer_server.core.privileged_client.shutil.which",
        lambda name: {"sss-helper": "/usr/local/bin/sss-helper", "sudo": "/usr/bin/sudo"}.get(name),
    )
    monkeypatch.setattr("simple_safer_server.core.privileged_client.os.geteuid", lambda: 1000)

    assert default_helper_command() == ["/usr/bin/sudo", "-n", "/usr/local/bin/sss-helper"]


def test_default_helper_command_uses_direct_helper_for_root(monkeypatch):
    monkeypatch.delenv("SSS_HELPER_COMMAND", raising=False)
    monkeypatch.setattr(
        "simple_safer_server.core.privileged_client.shutil.which",
        lambda name: {"sss-helper": "/usr/local/bin/sss-helper", "sudo": "/usr/bin/sudo"}.get(name),
    )
    monkeypatch.setattr("simple_safer_server.core.privileged_client.os.geteuid", lambda: 0)

    assert default_helper_command() == ["/usr/local/bin/sss-helper"]
