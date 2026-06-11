from dataclasses import dataclass
from typing import Any

from simple_safer_server.web.problems import (
    ForbiddenProblem,
    NotFoundProblem,
    OperationProblem,
    ValidationProblem,
)


@dataclass(frozen=True)
class AlertsList:
    alerts: list[dict[str, Any]]


@dataclass(frozen=True)
class AlertDetail:
    alert: dict[str, Any]


@dataclass(frozen=True)
class EmailConfig:
    config: dict[str, str]
    has_smtp_password: bool


class AlertsService:
    """Owns alert and email-notification settings that used to live in routes."""

    def __init__(self, runtime: Any, config_manager: Any, system_utils: Any) -> None:
        self._runtime = runtime
        self._config_manager = config_manager
        self._system_utils = system_utils

    def generate_test_alerts(self) -> None:
        if not self._runtime.is_fake:
            raise ForbiddenProblem(
                "Not available in production mode.",
                title="Fake mode required",
                slug="alerts-fake-mode-required",
            )

        long_scroll_test_message = "\n\n".join(
            [
                "This is an intentionally long fake-mode alert message for checking "
                "that the alert detail modal scrolls without hiding important controls.",
                "Section 1: The backup service reported a simulated sequence of "
                "status updates, retry notices, retention decisions, and final cleanup "
                "messages. Nothing here indicates a real failure; this text exists to "
                "exercise the UI with realistic operator-facing paragraphs.",
                "Section 2: Long alerts should remain readable on desktop and mobile. "
                "The title, metadata, message body, and modal actions should keep their "
                "spacing, and the close or mark-as-read controls should still be easy to "
                "reach after scrolling through the content.",
                "Section 3: This paragraph repeats enough detail to force vertical "
                "overflow in normal browser windows. It mentions mounted drives, Samba "
                "shares, scheduled tasks, email notification delivery, log collection, "
                "and stale lock cleanup so the message looks like a plausible combined "
                "system report rather than placeholder filler.",
                "Section 4: If the UI clips this message, fails to scroll, overlaps the "
                "footer, or loses focus handling, the generated test alert should make "
                "that problem obvious during manual fake-mode testing.",
                "Section 5: The simulated report continues with additional operational "
                "detail about rotating logs, pruning old backup snapshots, confirming "
                "configured notification recipients, checking available disk space, and "
                "recording the final task status for later review in the dashboard.",
                "Section 6: The message should also test wrapping for moderately long "
                "sentences that do not contain unusual punctuation or manual line breaks. "
                "Operators often paste complete command output or provider responses into "
                "diagnostic notes, so the modal should remain usable with dense prose.",
                "Section 7: Mobile browsers need the same coverage. A narrow viewport "
                "should allow the details panel to scroll smoothly while preserving readable "
                "line lengths, avoiding horizontal overflow, and keeping the surrounding "
                "metadata visually connected to the message body.",
                "Section 8: This final block is deliberately mundane because test content "
                "works best when it resembles real maintenance noise. It references cron "
                "timing, SMB availability checks, cloud sync retries, package update state, "
                "and alert delivery history to create enough height for scroll testing.",
            ]
        )

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
            long_scroll_test_message,
            alert_type="info",
            source="System Test",
        )
        return None

    def get_alerts(self) -> AlertsList:
        return AlertsList(alerts=self._config_manager.get_alerts())

    def get_alert(self, alert_id: int) -> AlertDetail:
        alerts = self._config_manager.get_alerts()
        alert = next((item for item in alerts if item["id"] == alert_id), None)
        if alert:
            return AlertDetail(alert=alert)
        raise NotFoundProblem("Alert not found.", title="Alert not found", slug="alert-not-found")

    def mark_alert_read(self, alert_id: int) -> None:
        if self._config_manager.mark_alert_read(alert_id):
            return None
        raise OperationProblem("Failed to mark alert as read.")

    def clear_alerts(self) -> None:
        if self._config_manager.clear_alerts():
            return None
        raise OperationProblem("Failed to clear alerts.")

    def mark_all_alerts_read(self) -> None:
        if self._config_manager.mark_all_alerts_read():
            return None
        raise OperationProblem("Failed to mark all alerts as read.")

    def get_email_config(self) -> EmailConfig:
        msmtp_config = self._read_msmtp_config()
        email_address = self._config_manager.get_value("backup", "email_address", "")
        from_address = self._config_manager.get_value("backup", "from_address", "")
        if email_address and "email_address" not in msmtp_config:
            msmtp_config["email_address"] = email_address
        if from_address and "from_address" not in msmtp_config:
            msmtp_config["from_address"] = from_address

        return EmailConfig(
            config=msmtp_config,
            has_smtp_password=bool(msmtp_config.get("smtp_password")),
        )

    def save_email_config(self, data: dict[str, Any]) -> None:
        email = data.get("email_address")
        from_address = data.get("from_address")
        smtp_server = data.get("smtp_server")
        smtp_port = data.get("smtp_port")
        smtp_username = data.get("smtp_username")
        smtp_password = (data.get("smtp_password") or "").strip()

        if not all([email, from_address, smtp_server, smtp_port, smtp_username]):
            raise ValidationProblem(
                "Email, from address, SMTP server, port, and username are required."
            )
        smtp_port_text = str(smtp_port).strip()
        if not smtp_port_text.isdigit() or not 1 <= int(smtp_port_text) <= 65535:
            raise ValidationProblem("SMTP port must be between 1 and 65535.")

        if not smtp_password:
            smtp_password = self._read_msmtp_config().get("smtp_password", "")
        if not smtp_password:
            raise ValidationProblem("SMTP password is required.")

        if not self._system_utils.write_msmtp_config(
            from_address, smtp_server, smtp_port_text, smtp_username, smtp_password
        ):
            raise OperationProblem("Failed to write msmtp configuration.")
        self._config_manager.set_value("backup", "email_address", email)
        self._config_manager.set_value("backup", "from_address", from_address)
        return None

    def _read_msmtp_config(self) -> dict[str, str]:
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
