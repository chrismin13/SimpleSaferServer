from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from simple_safer_server.services.pivpn_service import PiVpnService


def test_pivpn_status_reports_command_path_and_common_units():
    runtime = SimpleNamespace(is_fake=False)
    systemd_adapter = MagicMock()
    systemd_adapter.show_properties.side_effect = [
        "LoadState=loaded\nActiveState=active\nSubState=running\n",
        "LoadState=not-found\nActiveState=inactive\nSubState=dead\n",
        "LoadState=loaded\nActiveState=inactive\nSubState=dead\n",
    ]

    with patch(
        "simple_safer_server.services.pivpn_service.shutil.which",
        return_value="/usr/local/bin/pivpn",
    ):
        status = PiVpnService(runtime=runtime, systemd_adapter=systemd_adapter).get_page_status()

    assert status.installed is True
    assert status.install_status.label == "Installed"
    assert status.command_path == "/usr/local/bin/pivpn"
    assert status.wireguard_status.label == "Active"
    assert status.wireguard_status.unit_name == "wg-quick@wg0.service"
    assert status.openvpn_status.label == "Inactive"
    assert status.openvpn_status.unit_name == "openvpn.service"
    assert [command.command for command in status.commands] == [
        "pivpn -c",
        "pivpn -a",
        "pivpn -r",
        "pivpn -d",
    ]


def test_pivpn_status_handles_missing_install_and_units():
    runtime = SimpleNamespace(is_fake=False)
    systemd_adapter = MagicMock()
    systemd_adapter.show_properties.return_value = (
        "LoadState=not-found\nActiveState=inactive\nSubState=dead\n"
    )

    with patch("simple_safer_server.services.pivpn_service.shutil.which", return_value=None):
        status = PiVpnService(runtime=runtime, systemd_adapter=systemd_adapter).get_page_status()

    assert status.installed is False
    assert status.install_status.label == "Not found"
    assert status.wireguard_status.label == "Not found"
    assert status.openvpn_status.label == "Not found"
    assert "Checked common units" in status.openvpn_status.detail


def test_pivpn_fake_mode_does_not_call_system_commands():
    runtime = SimpleNamespace(is_fake=True)
    systemd_adapter = MagicMock()

    status = PiVpnService(runtime=runtime, systemd_adapter=systemd_adapter).get_page_status()

    assert status.installed is True
    assert status.install_status.label == "Demo mode"
    assert status.wireguard_status.label == "Active"
    systemd_adapter.show_properties.assert_not_called()
