from __future__ import annotations

from pathlib import Path
from typing import Any

from simple_safer_server.core.ownership import record_runtime_owned_resource
from simple_safer_server.core.privileged_actions import PrivilegedActionError
from simple_safer_server.services.file_persistence import (
    atomic_write_text,
    match_parent_owner_when_root,
)


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PrivilegedActionError(f"{key} is required.")
    value = value.strip()
    # This file is line-oriented. Newlines would let a field create extra
    # settings, so reject them before rendering the config.
    if "\n" in value or "\r" in value:
        raise PrivilegedActionError(f"{key} cannot contain line breaks.")
    return value


def render_smtp_config(
    *,
    from_address: str,
    server: str,
    port: str,
    username: str,
    password: str,
) -> str:
    return f"""defaults
port {port}
tls on
tls_trust_file /etc/ssl/certs/ca-certificates.crt

account simplesaferserver
host {server}
from {from_address}
auth on
user {username}
password {password}

account default : simplesaferserver
"""


def write_smtp_config_action(payload: dict[str, Any], runtime: Any) -> dict[str, Any]:
    from_address = _required_text(payload, "from_address")
    server = _required_text(payload, "smtp_server")
    port = _required_text(payload, "smtp_port")
    username = _required_text(payload, "smtp_username")
    password = _required_text(payload, "smtp_password")
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        raise PrivilegedActionError("SMTP port must be between 1 and 65535.")

    config_path = Path(runtime.smtp_config_path)
    atomic_write_text(
        config_path,
        render_smtp_config(
            from_address=from_address,
            server=server,
            port=port,
            username=username,
            password=password,
        ),
        mode=0o600,
    )
    match_parent_owner_when_root(config_path)
    record_runtime_owned_resource(
        runtime,
        "alerts",
        kind="config-file",
        identifier=str(config_path),
        reason="Store the SSS-owned SMTP settings used for alert email.",
    )
    return {"path": str(config_path)}
