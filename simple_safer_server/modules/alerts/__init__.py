"""Alerts module package."""

from simple_safer_server.modules.alerts.notifications import AlertNotifier
from simple_safer_server.modules.alerts.service import AlertsService
from simple_safer_server.modules.alerts.smtp_mailer import (
    SmtpAlertMailer,
    SmtpConfigError,
)

__all__ = [
    "AlertNotifier",
    "AlertsService",
    "SmtpAlertMailer",
    "SmtpConfigError",
]
