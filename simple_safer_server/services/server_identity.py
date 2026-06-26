import logging
import re
from dataclasses import dataclass
from typing import Any

from simple_safer_server.adapters.server_identity_commands import (
    ServerIdentityCommandAdapter,
)
from simple_safer_server.services.runtime import get_runtime

LOGGER = logging.getLogger(__name__)

SERVER_NAME_HELP_TEXT = (
    "This is the name shown in the Web UI and scheduled task alert email subjects."
)
SERVER_NAME_VALIDATION_MESSAGE = (
    "Server name may only contain letters, numbers, and hyphens, and cannot "
    "start or end with a hyphen."
)
MAX_HOSTNAME_LENGTH = 63
SERVER_NAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class ServerIdentityError(ValueError):
    """Raised when a server name cannot be saved safely."""


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
    """Normalize the UI server name into the app's safe single-label form."""
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


class ServerIdentityService:
    """Coordinates the SSS display name and read-only host identity."""

    def __init__(
        self,
        config_manager: Any,
        runtime: Any | None = None,
        command_adapter: Any | None = None,
    ) -> None:
        self.config_manager = config_manager
        self.runtime = runtime or get_runtime()
        self.command_adapter = command_adapter or ServerIdentityCommandAdapter()

    def current_identity(self) -> ServerIdentity:
        configured_name = self.config_manager.get_value("system", "server_name", "")
        hostname = configured_name
        if not self.runtime.is_fake:
            try:
                hostname = self.command_adapter.current_hostname()
            except Exception:
                LOGGER.exception("Failed to read current hostname")
        return ServerIdentity(server_name=configured_name or hostname, hostname=hostname)

    def save_server_name(self, value: Any) -> ServerIdentityUpdateResult:
        """Store the SSS server name without changing host OS identity."""
        server_name = normalize_server_name(value)
        self.config_manager.set_value("system", "server_name", server_name)
        hostname = server_name
        if not self.runtime.is_fake:
            try:
                hostname = self.command_adapter.current_hostname()
            except Exception:
                LOGGER.exception("Failed to read current hostname after saving server name")
        return ServerIdentityUpdateResult(server_name=server_name, hostname=hostname)
