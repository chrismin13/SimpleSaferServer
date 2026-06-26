import types

import pytest

from simple_safer_server.services.server_identity import (
    ServerIdentityError,
    ServerIdentityService,
    normalize_server_name,
)


class FakeConfigManager:
    def __init__(self):
        self.values = {"system": {}}

    def get_value(self, section, key, default=None):
        return self.values.get(section, {}).get(key, default)

    def set_value(self, section, key, value):
        self.values.setdefault(section, {})[key] = str(value)


class FakeServerIdentityCommands:
    def __init__(self, hostname="hostbox", fail_current=False):
        self.hostname = hostname
        self.fail_current = fail_current
        self.calls = []

    def current_hostname(self):
        self.calls.append(("current_hostname",))
        if self.fail_current:
            raise RuntimeError("hostname unavailable")
        return self.hostname


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


def test_current_identity_uses_saved_name_and_reads_hostname_in_real_mode():
    config = FakeConfigManager()
    config.set_value("system", "server_name", "family-nas")
    commands = FakeServerIdentityCommands(hostname="hostbox")
    service = ServerIdentityService(
        config,
        types.SimpleNamespace(is_fake=False),
        commands,
    )

    identity = service.current_identity()

    assert identity.server_name == "family-nas"
    assert identity.hostname == "hostbox"
    assert commands.calls == [("current_hostname",)]


def test_current_identity_falls_back_to_saved_name_when_hostname_is_unavailable():
    config = FakeConfigManager()
    config.set_value("system", "server_name", "family-nas")
    service = ServerIdentityService(
        config,
        types.SimpleNamespace(is_fake=False),
        FakeServerIdentityCommands(fail_current=True),
    )

    identity = service.current_identity()

    assert identity.server_name == "family-nas"
    assert identity.hostname == "family-nas"


def test_save_server_name_updates_only_sss_config_in_fake_mode():
    config = FakeConfigManager()
    commands = FakeServerIdentityCommands(hostname="real-host")
    service = ServerIdentityService(config, types.SimpleNamespace(is_fake=True), commands)

    result = service.save_server_name("Family-NAS")

    assert result.server_name == "family-nas"
    assert result.hostname == "family-nas"
    assert config.get_value("system", "server_name") == "family-nas"
    assert commands.calls == []


def test_save_server_name_keeps_os_hostname_read_only_in_real_mode():
    config = FakeConfigManager()
    commands = FakeServerIdentityCommands(hostname="hostbox")
    service = ServerIdentityService(config, types.SimpleNamespace(is_fake=False), commands)

    result = service.save_server_name("Family-NAS")

    assert result.server_name == "family-nas"
    assert result.hostname == "hostbox"
    assert config.get_value("system", "server_name") == "family-nas"
    assert commands.calls == [("current_hostname",)]
