import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple

from simple_safer_server.adapters.server_identity_commands import (
    ServerIdentityCommandAdapter,
)
from simple_safer_server.services.file_persistence import atomic_write_text
from simple_safer_server.services.runtime import get_runtime

LOGGER = logging.getLogger(__name__)

SERVER_NAME_HELP_TEXT = (
    "This is the name you'll use to find this server on your network. "
    "Scheduled task alert emails include it in the subject."
)
SERVER_NAME_VALIDATION_MESSAGE = (
    "Server name may only contain letters, numbers, and hyphens, and cannot "
    "start or end with a hyphen."
)
MAX_HOSTNAME_LENGTH = 63
LOCAL_HOSTS_ADDRESSES = {"127.0.0.1", "127.0.1.1"}
SERVER_NAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class ServerIdentityError(ValueError):
    """Raised when a server-name change cannot be applied safely."""


@dataclass(frozen=True)
class ServerIdentity:
    server_name: str
    hostname: str
    help_text: str = SERVER_NAME_HELP_TEXT

    def as_dict(self) -> Any:
        return {
            "server_name": self.server_name,
            "hostname": self.hostname,
            "help_text": self.help_text,
        }


@dataclass(frozen=True)
class ServerIdentityUpdateResult:
    server_name: str
    hostname: str
    warning: str = ""

    def as_dict(self) -> Any:
        payload = {
            "server_name": self.server_name,
            "hostname": self.hostname,
        }
        if self.warning:
            payload["warning"] = self.warning
        return payload


def normalize_server_name(value: Any) -> str:
    """Normalize the UI server name into a single-label Linux hostname."""
    if not isinstance(value, str):
        raise ServerIdentityError(SERVER_NAME_VALIDATION_MESSAGE)
    normalized = value.strip().lower()
    if not normalized:
        raise ServerIdentityError("Server name is required.")
    if len(normalized) > MAX_HOSTNAME_LENGTH:
        raise ServerIdentityError(f"Server name must be {MAX_HOSTNAME_LENGTH} characters or fewer.")
    if not SERVER_NAME_PATTERN.match(normalized):
        raise ServerIdentityError(SERVER_NAME_VALIDATION_MESSAGE)
    return normalized


def _split_hosts_line(line: str) -> Tuple[str, str]:
    if "#" not in line:
        return line.rstrip("\n"), ""
    body, comment = line.rstrip("\n").split("#", 1)
    return body.rstrip(), "#" + comment


def _join_hosts_line(address: str, names: List[str], comment: str) -> str:
    body = address
    if names:
        body = "{}\t{}".format(address, " ".join(names))
    if comment:
        body = f"{body} {comment}"
    return f"{body.rstrip()}\n"


def update_hosts_content(content: str, old_hostname: str, new_hostname: str) -> str:
    """Return `/etc/hosts` content with the local hostname entry updated.

    Only loopback hostname entries are touched. Unrelated addresses, aliases,
    comments, and custom host mappings are preserved because `/etc/hosts` is
    often hand-edited on home servers.
    """
    old_hostname = old_hostname.strip().lower()
    new_hostname = new_hostname.strip().lower()
    output = []
    updated_local_name = False
    saw_new_name = False

    for line in content.splitlines(True):
        body, comment = _split_hosts_line(line)
        tokens = body.split()
        if not tokens:
            output.append(line)
            continue

        address = tokens[0]
        names = tokens[1:]
        if address not in LOCAL_HOSTS_ADDRESSES:
            output.append(line)
            continue

        lowered_names = [name.lower() for name in names]
        if new_hostname in lowered_names:
            saw_new_name = True

        should_replace = old_hostname and old_hostname in lowered_names
        should_fill_127_0_1_1 = address == "127.0.1.1" and not names
        if should_replace or should_fill_127_0_1_1:
            replacement_names = []
            inserted = False
            for name in names:
                if name.lower() == old_hostname:
                    if not inserted:
                        replacement_names.append(new_hostname)
                        inserted = True
                    continue
                if name.lower() == new_hostname:
                    inserted = True
                replacement_names.append(name)
            if not inserted:
                replacement_names.insert(0, new_hostname)
            output.append(_join_hosts_line(address, replacement_names, comment))
            updated_local_name = True
            saw_new_name = True
            continue

        output.append(line)

    if not updated_local_name and not saw_new_name:
        output.append(f"127.0.1.1\t{new_hostname}\n")

    return "".join(output)


class ServerIdentityService:
    """Coordinates server-name config, OS hostname, hosts, and Samba discovery."""

    def __init__(
        self,
        config_manager: Any,
        runtime: Optional[Any] = None,
        command_adapter: Optional[Any] = None,
        hosts_path: Optional[Path] = None,
    ) -> None:
        self.config_manager = config_manager
        self.runtime = runtime or get_runtime()
        self.command_adapter = command_adapter or ServerIdentityCommandAdapter()
        self.hosts_path = hosts_path or Path("/etc/hosts")

    def current_identity(self) -> ServerIdentity:
        configured_name = self.config_manager.get_value("system", "server_name", "")
        hostname = configured_name
        if not self.runtime.is_fake:
            try:
                hostname = self.command_adapter.current_hostname()
            except Exception:
                LOGGER.exception("Failed to read current hostname")
        return ServerIdentity(server_name=configured_name or hostname, hostname=hostname)

    def update_server_name(
        self, value: Any, *, restart_samba: bool = True
    ) -> ServerIdentityUpdateResult:
        new_hostname = normalize_server_name(value)
        current_hostname = self._current_hostname_for_update()
        previous_hosts_content = None

        if not self.runtime.is_fake:
            previous_hosts_content = self._update_hosts_file(current_hostname, new_hostname)
            try:
                self.command_adapter.set_hostname(new_hostname)
            except Exception as exc:
                self._restore_hosts_file(previous_hosts_content)
                raise ServerIdentityError("Could not update the system hostname.") from exc

        self._persist_hostname_metadata(current_hostname, new_hostname)

        warning = ""
        if restart_samba:
            warning = self._restart_samba_services()

        return ServerIdentityUpdateResult(
            server_name=new_hostname,
            hostname=new_hostname,
            warning=warning,
        )

    def _current_hostname_for_update(self) -> str:
        if self.runtime.is_fake:
            return self.config_manager.get_value(
                "system", "applied_hostname", ""
            ) or self.config_manager.get_value("system", "server_name", "")
        return self.command_adapter.current_hostname()

    def _update_hosts_file(self, old_hostname: str, new_hostname: str) -> str:
        try:
            content = self.hosts_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            content = ""
        updated = update_hosts_content(content, old_hostname, new_hostname)
        if updated != content:
            backup_path = self.hosts_path.with_name(f"{self.hosts_path.name}.SimpleSaferServer.bak")
            if content and not backup_path.exists():
                atomic_write_text(backup_path, content, mode=0o644)
            atomic_write_text(self.hosts_path, updated, mode=0o644)
        return content

    def _restore_hosts_file(self, content: Optional[str]) -> None:
        if content is None:
            return
        try:
            atomic_write_text(self.hosts_path, content, mode=0o644)
        except Exception:
            LOGGER.exception("Failed to restore %s after hostname update failure", self.hosts_path)

    def _persist_hostname_metadata(self, original_hostname: str, new_hostname: str) -> None:
        if (
            str(self.config_manager.get_value("system", "hostname_managed", "false")).lower()
            != "true"
        ):
            self.config_manager.set_value("system", "original_hostname", original_hostname)
        self.config_manager.set_value("system", "server_name", new_hostname)
        self.config_manager.set_value("system", "hostname_managed", "true")
        self.config_manager.set_value("system", "applied_hostname", new_hostname)

    def _restart_samba_services(self) -> str:
        if self.runtime.is_fake:
            return ""
        failed_units = []
        for unit_name in ("smbd", "nmbd"):
            try:
                self.command_adapter.restart_unit(unit_name)
            except Exception:
                LOGGER.exception("Failed to restart %s after hostname change", unit_name)
                failed_units.append(unit_name)
        if failed_units:
            return (
                "Server name was updated, but file sharing services did not restart cleanly. "
                "Restart Samba manually if the old name still appears on the network."
            )
        return ""
