import json
import subprocess
from unittest.mock import patch

from simple_safer_server.services.tailscale import TailscaleService


class FakeCommandRunner:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return self.result


class RaisingCommandRunner:
    def run(self, command, **kwargs):
        raise subprocess.TimeoutExpired(command, timeout=kwargs["timeout"])


def completed_status(payload):
    return subprocess.CompletedProcess(
        ["tailscale", "status", "--json"],
        0,
        stdout=json.dumps(payload),
        stderr="",
    )


def test_summary_uses_magicdns_name_and_tailscale_ips():
    runner = FakeCommandRunner(
        completed_status(
            {
                "BackendState": "Running",
                "MagicDNSSuffix": "tailnet.ts.net.",
                "Self": {
                    "HostName": "family-nas",
                    "DNSName": "family-nas.tailnet.ts.net.",
                    "TailscaleIPs": ["100.64.0.8", "fd7a:115c:a1e0::8"],
                },
            }
        )
    )

    with patch(
        "simple_safer_server.services.tailscale.shutil.which", return_value="/usr/bin/tailscale"
    ):
        summary = TailscaleService(runner).get_summary()

    assert summary.status == "connected"
    assert summary.dns_names == ["family-nas.tailnet.ts.net"]
    assert summary.ips == ["100.64.0.8", "fd7a:115c:a1e0::8"]
    assert summary.access_urls == [
        "http://family-nas.tailnet.ts.net:5000",
        "http://100.64.0.8:5000",
        "http://[fd7a:115c:a1e0::8]:5000",
    ]
    assert runner.calls[0][1]["timeout"] == 5


def test_summary_builds_dns_name_from_magicdns_suffix_when_dnsname_is_missing():
    runner = FakeCommandRunner(
        completed_status(
            {
                "BackendState": "Running",
                "MagicDNSSuffix": "tailnet.ts.net",
                "Self": {
                    "HostName": "family-nas",
                    "TailscaleIPs": ["100.64.0.8"],
                },
            }
        )
    )

    with patch(
        "simple_safer_server.services.tailscale.shutil.which", return_value="/usr/bin/tailscale"
    ):
        summary = TailscaleService(runner).get_summary()

    assert summary.dns_names == ["family-nas.tailnet.ts.net"]
    assert summary.access_urls[0] == "http://family-nas.tailnet.ts.net:5000"


def test_summary_reports_not_installed_without_running_tailscale():
    runner = FakeCommandRunner(completed_status({}))

    with patch("simple_safer_server.services.tailscale.shutil.which", return_value=None):
        summary = TailscaleService(runner).get_summary()

    assert summary.status == "not_installed"
    assert runner.calls == []


def test_summary_reports_unavailable_when_tailscale_command_times_out():
    with patch(
        "simple_safer_server.services.tailscale.shutil.which", return_value="/usr/bin/tailscale"
    ):
        summary = TailscaleService(RaisingCommandRunner()).get_summary()

    assert summary.status == "unavailable"
    assert "timed out" in summary.message
