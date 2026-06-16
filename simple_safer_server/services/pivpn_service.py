import shutil
from dataclasses import dataclass
from typing import Any

PIVPN_DOCS_URL = "https://docs.pivpn.io/"
PIVPN_SSS_DOCS_URL = "https://github.com/chrismin13/SimpleSaferServer/blob/main/docs/pivpn.md"

WIREGUARD_UNITS = ("wg-quick@wg0.service",)
OPENVPN_UNITS = ("openvpn@server.service", "openvpn.service")


@dataclass(frozen=True)
class PiVpnServiceStatus:
    """A small service status value that templates can render directly."""

    label: str
    badge_class: str
    detail: str
    unit_name: str | None = None


@dataclass(frozen=True)
class PiVpnCommand:
    """A terminal command worth showing without running it from the web page."""

    label: str
    command: str
    description: str


@dataclass(frozen=True)
class PiVpnPageStatus:
    installed: bool
    install_status: PiVpnServiceStatus
    wireguard_status: PiVpnServiceStatus
    openvpn_status: PiVpnServiceStatus
    command_path: str | None
    commands: tuple[PiVpnCommand, ...]
    docs_url: str = PIVPN_DOCS_URL
    app_docs_url: str = PIVPN_SSS_DOCS_URL


class PiVpnService:
    """Builds the read-only PiVPN page state."""

    def __init__(self, runtime: Any, systemd_adapter: Any) -> None:
        self._runtime = runtime
        self._systemd_adapter = systemd_adapter

    def get_page_status(self) -> PiVpnPageStatus:
        if self._runtime.is_fake:
            return self._fake_status()

        command_path = shutil.which("pivpn")
        installed = command_path is not None
        install_status = (
            PiVpnServiceStatus("Installed", "badge-success", command_path or "pivpn found")
            if installed
            else PiVpnServiceStatus(
                "Not found",
                "badge-warning",
                "Install PiVPN first, then come back here for status and commands.",
            )
        )

        return PiVpnPageStatus(
            installed=installed,
            install_status=install_status,
            wireguard_status=self._first_loaded_unit_status("WireGuard", WIREGUARD_UNITS),
            openvpn_status=self._first_loaded_unit_status("OpenVPN", OPENVPN_UNITS),
            command_path=command_path,
            commands=PiVpnService.default_commands(),
        )

    @staticmethod
    def default_commands() -> tuple[PiVpnCommand, ...]:
        return (
            PiVpnCommand("List clients", "pivpn -c", "Show configured VPN clients."),
            PiVpnCommand("Add client", "pivpn -a", "Create a new VPN client profile."),
            PiVpnCommand("Remove client", "pivpn -r", "Revoke a VPN client profile."),
            PiVpnCommand("Debug", "pivpn -d", "Run PiVPN's built-in diagnostic check."),
        )

    def _fake_status(self) -> PiVpnPageStatus:
        return PiVpnPageStatus(
            installed=True,
            install_status=PiVpnServiceStatus(
                "Demo mode",
                "badge-info",
                "Fake mode shows what the PiVPN page looks like without reading this system.",
            ),
            wireguard_status=PiVpnServiceStatus(
                "Active",
                "badge-success",
                "Fake WireGuard status",
                "wg-quick@wg0.service",
            ),
            openvpn_status=PiVpnServiceStatus(
                "Not found",
                "badge-neutral",
                "Fake mode does not include an OpenVPN unit.",
            ),
            command_path="/usr/local/bin/pivpn",
            commands=PiVpnService.default_commands(),
        )

    def _first_loaded_unit_status(
        self, service_name: str, unit_names: tuple[str, ...]
    ) -> PiVpnServiceStatus:
        for unit_name in unit_names:
            status = self._unit_status(service_name, unit_name)
            if status.label != "Not found":
                return status

        checked = ", ".join(unit_names)
        return PiVpnServiceStatus(
            "Not found",
            "badge-neutral",
            f"Checked common units: {checked}",
        )

    def _unit_status(self, service_name: str, unit_name: str) -> PiVpnServiceStatus:
        try:
            properties = self._parse_systemd_properties(
                self._systemd_adapter.show_properties(
                    unit_name,
                    "LoadState",
                    "ActiveState",
                    "SubState",
                )
            )
        except Exception:
            return PiVpnServiceStatus(
                "Unknown",
                "badge-warning",
                f"Could not read {unit_name}.",
                unit_name,
            )

        load_state = properties.get("LoadState", "")
        active_state = properties.get("ActiveState", "")
        sub_state = properties.get("SubState", "")
        if load_state == "not-found":
            return PiVpnServiceStatus("Not found", "badge-neutral", f"{unit_name} is not loaded.")
        if active_state == "active":
            return PiVpnServiceStatus(
                "Active",
                "badge-success",
                f"{service_name} is running through {unit_name}.",
                unit_name,
            )
        if active_state == "inactive":
            return PiVpnServiceStatus(
                "Inactive",
                "badge-warning",
                f"{unit_name} is installed but not running.",
                unit_name,
            )
        if active_state == "failed":
            return PiVpnServiceStatus(
                "Failed",
                "badge-danger",
                f"{unit_name} is in failed state.",
                unit_name,
            )
        state_text = " / ".join(part for part in (load_state, active_state, sub_state) if part)
        return PiVpnServiceStatus(
            "Unknown",
            "badge-warning",
            state_text or f"{unit_name} returned no status.",
            unit_name,
        )

    @staticmethod
    def _parse_systemd_properties(output: str) -> dict[str, str]:
        properties: dict[str, str] = {}
        for line in output.splitlines():
            key, separator, value = line.partition("=")
            if separator:
                properties[key] = value
        return properties
