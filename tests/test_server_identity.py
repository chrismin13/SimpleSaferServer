import subprocess
import types
from pathlib import Path

import pytest

from simple_safer_server.services.server_identity import (
    ServerIdentityError,
    ServerIdentityService,
    normalize_server_name,
    update_hosts_content,
)


class FakeConfigManager:
    def __init__(self):
        self.values = {"system": {}}

    def get_value(self, section, key, default=None):
        return self.values.get(section, {}).get(key, default)

    def set_value(self, section, key, value):
        self.values.setdefault(section, {})[key] = str(value)


class FakeServerIdentityCommands:
    def __init__(self, hostname="oldbox", fail_set=False, fail_restart_units=None):
        self.hostname = hostname
        self.fail_set = fail_set
        self.fail_restart_units = set(fail_restart_units or [])
        self.calls = []

    def current_hostname(self):
        self.calls.append(("current_hostname",))
        return self.hostname

    def set_hostname(self, hostname):
        self.calls.append(("set_hostname", hostname))
        if self.fail_set:
            raise subprocess.CalledProcessError(1, ["hostnamectl"])
        self.hostname = hostname

    def restart_unit(self, unit_name):
        self.calls.append(("restart_unit", unit_name))
        if unit_name in self.fail_restart_units:
            raise subprocess.CalledProcessError(1, ["systemctl", "restart", unit_name])


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("simple-safer", "simple-safer"),
        (" Simple-Safer ", "simple-safer"),
        ("nas01", "nas01"),
    ],
)
def test_normalize_server_name_accepts_supported_names(value, expected):
    assert normalize_server_name(value) == expected


@pytest.mark.parametrize("value", ["", "bad name", "bad_name", "-bad", "bad-", "bad.name"])
def test_normalize_server_name_rejects_invalid_names(value):
    with pytest.raises(ServerIdentityError):
        normalize_server_name(value)


def test_update_hosts_content_replaces_local_hostname_entry():
    content = "127.0.0.1 localhost\n127.0.1.1 oldbox oldalias # keep\n10.0.0.5 oldbox\n"

    updated = update_hosts_content(content, "oldbox", "newbox")

    assert "127.0.1.1\tnewbox oldalias # keep\n" in updated
    assert "10.0.0.5 oldbox\n" in updated


def test_update_hosts_content_adds_local_entry_when_missing():
    updated = update_hosts_content("127.0.0.1 localhost\n", "oldbox", "newbox")

    assert updated.endswith("127.0.1.1\tnewbox\n")


def test_update_server_name_updates_hostname_config_hosts_and_samba(tmp_path):
    config = FakeConfigManager()
    commands = FakeServerIdentityCommands(hostname="oldbox")
    hosts_path = tmp_path / "hosts"
    hosts_path.write_text("127.0.0.1 localhost\n127.0.1.1 oldbox\n")
    runtime = types.SimpleNamespace(is_fake=False)
    service = ServerIdentityService(config, runtime, commands, hosts_path)

    result = service.update_server_name("NewBox")

    assert result.server_name == "newbox"
    assert config.get_value("system", "server_name") == "newbox"
    assert config.get_value("system", "hostname_managed") == "true"
    assert config.get_value("system", "original_hostname") == "oldbox"
    assert config.get_value("system", "applied_hostname") == "newbox"
    assert "127.0.1.1\tnewbox\n" in hosts_path.read_text()
    assert ("set_hostname", "newbox") in commands.calls
    assert ("restart_unit", "smbd") in commands.calls
    assert ("restart_unit", "nmbd") in commands.calls


def test_update_server_name_preserves_original_hostname_on_later_edits(tmp_path):
    config = FakeConfigManager()
    config.set_value("system", "hostname_managed", "true")
    config.set_value("system", "original_hostname", "oldbox")
    commands = FakeServerIdentityCommands(hostname="middlebox")
    hosts_path = tmp_path / "hosts"
    hosts_path.write_text("127.0.1.1 middlebox\n")
    runtime = types.SimpleNamespace(is_fake=False)
    service = ServerIdentityService(config, runtime, commands, hosts_path)

    service.update_server_name("newbox", restart_samba=False)

    assert config.get_value("system", "original_hostname") == "oldbox"
    assert config.get_value("system", "applied_hostname") == "newbox"


def test_update_server_name_rolls_back_hosts_when_hostname_command_fails(tmp_path):
    config = FakeConfigManager()
    commands = FakeServerIdentityCommands(hostname="oldbox", fail_set=True)
    hosts_path = tmp_path / "hosts"
    original_hosts = "127.0.0.1 localhost\n127.0.1.1 oldbox\n"
    hosts_path.write_text(original_hosts)
    runtime = types.SimpleNamespace(is_fake=False)
    service = ServerIdentityService(config, runtime, commands, hosts_path)

    with pytest.raises(ServerIdentityError):
        service.update_server_name("newbox")

    assert hosts_path.read_text() == original_hosts
    assert config.get_value("system", "server_name") is None


def test_update_server_name_returns_warning_when_samba_restart_fails(tmp_path):
    config = FakeConfigManager()
    commands = FakeServerIdentityCommands(hostname="oldbox", fail_restart_units={"nmbd"})
    hosts_path = tmp_path / "hosts"
    hosts_path.write_text("127.0.1.1 oldbox\n")
    runtime = types.SimpleNamespace(is_fake=False)
    service = ServerIdentityService(config, runtime, commands, hosts_path)

    result = service.update_server_name("newbox")

    assert result.warning
    assert config.get_value("system", "server_name") == "newbox"


def test_update_server_name_fake_mode_updates_config_without_commands(tmp_path):
    config = FakeConfigManager()
    config.set_value("system", "server_name", "oldbox")
    commands = FakeServerIdentityCommands(hostname="real-host")
    runtime = types.SimpleNamespace(is_fake=True)
    service = ServerIdentityService(config, runtime, commands, Path(tmp_path / "hosts"))

    service.update_server_name("newbox")

    assert config.get_value("system", "server_name") == "newbox"
    assert commands.calls == []
