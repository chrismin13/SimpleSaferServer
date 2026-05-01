from typing import Any, Dict, Tuple


class AlertsService:
    """Owns alert and email-notification settings that used to live in routes."""

    def __init__(self, runtime: Any, config_manager: Any, system_utils: Any) -> None:
        self._runtime = runtime
        self._config_manager = config_manager
        self._system_utils = system_utils

    def generate_test_alerts(self) -> Tuple[Dict[str, Any], int]:
        if not self._runtime.is_fake:
            return {"success": False, "error": "Not available in production mode"}, 403
        self._config_manager.log_alert(
            "Test Error",
            "This is a simulated error message to verify UI styling.",
            alert_type="error",
            source="System Test",
        )
        self._config_manager.log_alert(
            "Test Warning",
            "This is a simulated warning message. Things might be wrong.",
            alert_type="warning",
            source="System Test",
        )
        self._config_manager.log_alert(
            "Test Success",
            "This is a simulated success message. Everything is great!",
            alert_type="success",
            source="System Test",
        )
        self._config_manager.log_alert(
            "Test Info",
            "This is a simulated info message just letting you know something happened.",
            alert_type="info",
            source="System Test",
        )
        return {"success": True}, 200

    def get_alerts(self) -> Dict[str, Any]:
        return {"success": True, "alerts": self._config_manager.get_alerts()}

    def get_alert(self, alert_id: int) -> Tuple[Dict[str, Any], int]:
        alerts = self._config_manager.get_alerts()
        alert = next((item for item in alerts if item["id"] == alert_id), None)
        if alert:
            return {"success": True, "alert": alert}, 200
        return {"success": False, "error": "Alert not found"}, 404

    def mark_alert_read(self, alert_id: int) -> Dict[str, Any]:
        if self._config_manager.mark_alert_read(alert_id):
            return {"success": True}
        return {"success": False, "error": "Failed to mark alert as read"}

    def clear_alerts(self) -> Dict[str, Any]:
        if self._config_manager.clear_alerts():
            return {"success": True}
        return {"success": False, "error": "Failed to clear alerts"}

    def mark_all_alerts_read(self) -> Dict[str, Any]:
        if self._config_manager.mark_all_alerts_read():
            return {"success": True}
        return {"success": False, "error": "Failed to mark all alerts as read"}

    def get_email_config(self) -> Dict[str, Any]:
        msmtp_config = self._read_msmtp_config()
        email_address = self._config_manager.get_value("backup", "email_address", "")
        from_address = self._config_manager.get_value("backup", "from_address", "")
        if email_address and "email_address" not in msmtp_config:
            msmtp_config["email_address"] = email_address
        if from_address and "from_address" not in msmtp_config:
            msmtp_config["from_address"] = from_address

        return {
            "success": True,
            "config": msmtp_config,
            "has_smtp_password": bool(msmtp_config.get("smtp_password")),
        }

    def save_email_config(self, data: Dict[str, Any]) -> Dict[str, Any]:
        email = data.get("email_address")
        from_address = data.get("from_address")
        smtp_server = data.get("smtp_server")
        smtp_port = data.get("smtp_port")
        smtp_username = data.get("smtp_username")
        smtp_password = (data.get("smtp_password") or "").strip()

        if not all([email, from_address, smtp_server, smtp_port, smtp_username]):
            return {
                "success": False,
                "error": "Email, from address, SMTP server, port, and username are required",
            }
        smtp_port_text = str(smtp_port).strip()
        if not smtp_port_text.isdigit() or not 1 <= int(smtp_port_text) <= 65535:
            return {"success": False, "error": "SMTP port must be between 1 and 65535"}

        if not smtp_password:
            smtp_password = self._read_msmtp_config().get("smtp_password", "")
        if not smtp_password:
            return {"success": False, "error": "SMTP password is required"}

        self._config_manager.set_value("backup", "email_address", email)
        self._config_manager.set_value("backup", "from_address", from_address)
        if not self._system_utils.write_msmtp_config(
            from_address, smtp_server, smtp_port_text, smtp_username, smtp_password
        ):
            return {"success": False, "error": "Failed to write msmtp configuration"}
        return {"success": True}

    def _read_msmtp_config(self) -> Dict[str, str]:
        msmtp_config = {}
        try:
            with open(self._runtime.msmtp_config_path) as config_file:
                content = config_file.read()
        except FileNotFoundError:
            return msmtp_config

        for raw_line in content.split("\n"):
            line = raw_line.strip()
            if line.startswith("host "):
                msmtp_config["smtp_server"] = line.split(" ", 1)[1]
            elif line.startswith("port "):
                msmtp_config["smtp_port"] = line.split(" ", 1)[1]
            elif line.startswith("from "):
                msmtp_config["from_address"] = line.split(" ", 1)[1]
            elif line.startswith("user "):
                msmtp_config["smtp_username"] = line.split(" ", 1)[1]
            elif line.startswith("password "):
                msmtp_config["smtp_password"] = line.split(" ", 1)[1]

        return msmtp_config
