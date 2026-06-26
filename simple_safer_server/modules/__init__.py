"""Feature modules that keep behavior, setup plans, jobs, and UI help together."""

from __future__ import annotations

from collections.abc import Sequence

from flask import Blueprint


def module_blueprints() -> Sequence[Blueprint]:
    """Return module-owned Flask blueprints in startup registration order."""
    from simple_safer_server.modules.alerts.routes import alerts
    from simple_safer_server.modules.cloud_backup.routes import cloud_backup
    from simple_safer_server.modules.ddns.routes import ddns
    from simple_safer_server.modules.drive_health.routes import drive_health
    from simple_safer_server.modules.file_sharing.routes import smb
    from simple_safer_server.modules.storage.routes import storage
    from simple_safer_server.modules.system_updates.routes import system_updates

    return (
        ddns,
        cloud_backup,
        system_updates,
        alerts,
        smb,
        storage,
        drive_health,
    )
