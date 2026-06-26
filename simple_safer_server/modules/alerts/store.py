from datetime import datetime
from pathlib import Path
from typing import Any

from simple_safer_server.services.file_persistence import (
    atomic_write_json,
    locked_json_update,
    locked_path,
    read_json,
)


class AlertStore:
    """Persist alerts with cross-process locking and atomic JSON replacement."""

    def __init__(self, alerts_path: Path):
        self.alerts_path = alerts_path
        self.lock_path = alerts_path.with_suffix(".lock")

    def initialize(self) -> None:
        # Initialization uses the same stable sidecar lock as updates so a
        # first-run script cannot overwrite another process's freshly appended alert.
        with locked_path(self.lock_path, mode=0o644):
            if not self.alerts_path.exists():
                atomic_write_json(self.alerts_path, [], mode=0o644)
            else:
                self.alerts_path.chmod(0o644)

    def list_alerts(
        self, limit: int | None = None, unread_only: bool = False
    ) -> list[dict[str, Any]]:
        alerts = read_json(self.alerts_path, [])
        if unread_only:
            alerts = [alert for alert in alerts if not alert.get("read", False)]
        if limit:
            alerts = alerts[-limit:]
        return alerts

    def append_alert(
        self,
        title: str,
        message: str,
        alert_type: str = "info",
        source: str = "system",
    ) -> dict[str, Any]:
        new_alert = {}

        def update(alerts):
            next_id = (
                max(
                    (
                        existing_alert.get("id", 0)
                        for existing_alert in alerts
                        if isinstance(existing_alert.get("id"), int)
                    ),
                    default=0,
                )
                + 1
            )
            alert = {
                # IDs stay monotonic even after retention trims old alerts.
                "id": next_id,
                "title": title,
                "message": message,
                "type": alert_type,
                "source": source,
                "timestamp": datetime.now().isoformat(),
                "read": False,
            }
            alerts.append(alert)
            if len(alerts) > 1000:
                alerts = alerts[-1000:]
            new_alert.update(alert)
            return alerts

        locked_json_update(
            self.alerts_path,
            self.lock_path,
            [],
            update,
            file_mode=0o644,
            lock_mode=0o644,
        )
        return new_alert

    def mark_alert_read(self, alert_id: int) -> None:
        def update(alerts):
            for alert in alerts:
                if alert["id"] == alert_id:
                    alert["read"] = True
                    break
            return alerts

        locked_json_update(
            self.alerts_path,
            self.lock_path,
            [],
            update,
            file_mode=0o644,
            lock_mode=0o644,
        )

    def clear(self) -> None:
        def update(_alerts):
            return []

        locked_json_update(
            self.alerts_path,
            self.lock_path,
            [],
            update,
            file_mode=0o644,
            lock_mode=0o644,
        )

    def mark_all_read(self) -> None:
        def update(alerts):
            for alert in alerts:
                alert["read"] = True
            return alerts

        locked_json_update(
            self.alerts_path,
            self.lock_path,
            [],
            update,
            file_mode=0o644,
            lock_mode=0o644,
        )
