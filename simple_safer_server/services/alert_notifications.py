import logging
from typing import Any

from simple_safer_server.adapters.command_runner import CalledProcessError, TimeoutExpired
from simple_safer_server.adapters.drive_health_commands import DriveHealthCommandAdapter

LOGGER = logging.getLogger(__name__)


class AlertNotifier:
    def __init__(
        self,
        config_manager: Any,
        runtime: Any,
        command_adapter: DriveHealthCommandAdapter | None = None,
        logger: Any | None = None,
    ) -> None:
        self._config_manager = config_manager
        self._runtime = runtime
        self._command_adapter = command_adapter or DriveHealthCommandAdapter()
        self._logger = logger or LOGGER

    def notify(self, title: str, message: str, *, alert_type: str, source: str) -> None:
        self._config_manager.log_alert(title, message, alert_type=alert_type, source=source)

        if self._runtime.is_fake:
            self._logger.info("Fake mode: suppressing email for alert '%s'", title)
            return

        email_address = (
            self._config_manager.get_value("backup", "email_address", "") or ""
        ).strip()
        from_address = (self._config_manager.get_value("backup", "from_address", "") or "").strip()
        server_name = (
            self._config_manager.get_value("system", "server_name", "SimpleSaferServer")
            or "SimpleSaferServer"
        ).strip()
        if not email_address or not from_address:
            self._logger.warning("Skipping email alert because email settings are incomplete.")
            return

        email_body = f"Subject: {title} - {server_name}\nFrom: {from_address}\n\n{message}"
        try:
            self._command_adapter.send_email(from_address, email_address, email_body)
        except (CalledProcessError, OSError, TimeoutExpired) as exc:
            self._logger.warning("Failed to send alert email '%s': %s", title, exc)
