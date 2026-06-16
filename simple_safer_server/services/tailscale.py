import json
import shutil
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Any

from simple_safer_server.adapters.command_runner import CommandRunner, SubprocessError

WEB_UI_PORT = 5000


@dataclass(frozen=True)
class TailscaleSummary:
    """Read-only Tailscale state shown to local administrators."""

    status: str
    status_label: str
    message: str
    backend_state: str
    hostname: str
    dns_names: list[str]
    ips: list[str]
    access_urls: list[str]


class TailscaleService:
    """Collects Tailscale access details without configuring the tailnet."""

    def __init__(self, command_runner: CommandRunner) -> None:
        self._command_runner = command_runner

    def get_summary(self) -> TailscaleSummary:
        if shutil.which("tailscale") is None:
            return TailscaleSummary(
                status="not_installed",
                status_label="Not Installed",
                message="Tailscale is not installed on this server.",
                backend_state="",
                hostname="",
                dns_names=[],
                ips=[],
                access_urls=[],
            )

        try:
            result = self._command_runner.run(
                ["tailscale", "status", "--json"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, SubprocessError) as exc:
            return TailscaleSummary(
                status="unavailable",
                status_label="Unavailable",
                message=f"Could not run tailscale: {exc}",
                backend_state="",
                hostname="",
                dns_names=[],
                ips=[],
                access_urls=[],
            )

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "tailscale status failed").strip()
            return TailscaleSummary(
                status="unavailable",
                status_label="Unavailable",
                message=detail,
                backend_state="",
                hostname="",
                dns_names=[],
                ips=[],
                access_urls=[],
            )

        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return TailscaleSummary(
                status="unavailable",
                status_label="Unavailable",
                message="Tailscale returned status data that could not be read.",
                backend_state="",
                hostname="",
                dns_names=[],
                ips=[],
                access_urls=[],
            )

        return self._summary_from_status(payload)

    def _summary_from_status(self, payload: dict[str, Any]) -> TailscaleSummary:
        backend_state = str(payload.get("BackendState") or "")
        self_node = payload.get("Self") if isinstance(payload.get("Self"), dict) else {}
        hostname = str(self_node.get("HostName") or "").strip()
        dns_names = _tailscale_dns_names(payload)
        ips = _tailscale_ips(self_node)
        access_urls = _access_urls(dns_names, ips)
        connected = backend_state.lower() == "running" and bool(dns_names or ips)

        if connected:
            return TailscaleSummary(
                status="connected",
                status_label="Connected",
                message="Tailscale is installed and logged in.",
                backend_state=backend_state,
                hostname=hostname,
                dns_names=dns_names,
                ips=ips,
                access_urls=access_urls,
            )

        return TailscaleSummary(
            status="not_connected",
            status_label="Not Connected",
            message="Tailscale is installed, but this server is not connected to a tailnet.",
            backend_state=backend_state,
            hostname=hostname,
            dns_names=dns_names,
            ips=ips,
            access_urls=access_urls,
        )


def _clean_dns_name(value: Any) -> str:
    return str(value or "").strip().rstrip(".")


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _tailscale_dns_names(payload: dict[str, Any]) -> list[str]:
    self_node = payload.get("Self") if isinstance(payload.get("Self"), dict) else {}
    dns_names: list[str] = []
    _append_unique(dns_names, _clean_dns_name(self_node.get("DNSName")))

    hostname = _clean_dns_name(self_node.get("HostName"))
    suffix = _clean_dns_name(payload.get("MagicDNSSuffix"))
    if hostname and suffix:
        # Some Tailscale versions include DNSName, others only expose the
        # MagicDNS suffix. Build the same FQDN when both pieces are present.
        _append_unique(dns_names, f"{hostname}.{suffix}")

    return dns_names


def _tailscale_ips(self_node: dict[str, Any]) -> list[str]:
    raw_ips = self_node.get("TailscaleIPs")
    if not isinstance(raw_ips, list):
        return []
    return [str(raw_ip).strip() for raw_ip in raw_ips if str(raw_ip).strip()]


def _access_urls(dns_names: list[str], ips: list[str]) -> list[str]:
    urls: list[str] = []
    for dns_name in dns_names:
        urls.append(f"http://{dns_name}:{WEB_UI_PORT}")
    for ip in ips:
        try:
            parsed = ip_address(ip)
        except ValueError:
            continue
        host = f"[{ip}]" if parsed.version == 6 else ip
        urls.append(f"http://{host}:{WEB_UI_PORT}")
    return urls
