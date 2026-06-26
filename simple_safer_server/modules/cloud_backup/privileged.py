from __future__ import annotations

from pathlib import Path
from typing import Any

from simple_safer_server.core.ownership import record_runtime_owned_resource
from simple_safer_server.core.privileged_actions import PrivilegedActionError
from simple_safer_server.services.file_persistence import (
    atomic_write_text,
    match_parent_owner_when_root,
)


def write_rclone_config_action(payload: dict[str, Any], runtime: Any) -> dict[str, Any]:
    rclone_config = payload.get("rclone_config")
    if not isinstance(rclone_config, str) or not rclone_config.strip():
        raise PrivilegedActionError("rclone_config is required.")
    if "\x00" in rclone_config:
        raise PrivilegedActionError("rclone_config cannot contain NUL bytes.")

    config_path = Path(runtime.rclone_config_dir) / "rclone.conf"
    atomic_write_text(config_path, rclone_config, mode=0o600)
    match_parent_owner_when_root(config_path)
    record_runtime_owned_resource(
        runtime,
        "cloud-backup",
        kind="config-file",
        identifier=str(config_path),
        reason="Keep SSS cloud backup separate from root's global rclone config.",
    )
    return {"path": str(config_path)}
