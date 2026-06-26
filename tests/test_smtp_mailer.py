from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from simple_safer_server.modules.alerts.smtp_mailer import (
    SmtpAlertMailer,
    SmtpConfigError,
    load_smtp_config,
    read_smtp_config,
)


def test_read_smtp_config_parses_smtp_file(tmp_path):
    config_path = tmp_path / "smtp.conf"
    config_path.write_text(
        "\n".join(
            [
                "defaults",
                "port 587",
                "host smtp.example.com",
                "from server@example.com",
                "user server",
                "password secret",
            ]
        ),
        encoding="utf-8",
    )

    config = read_smtp_config(config_path)

    assert config == {
        "smtp_port": "587",
        "smtp_server": "smtp.example.com",
        "from_address": "server@example.com",
        "smtp_username": "server",
        "smtp_password": "secret",
    }


def test_load_smtp_config_rejects_missing_values(tmp_path):
    config_path = tmp_path / "smtp.conf"
    config_path.write_text("host smtp.example.com\n", encoding="utf-8")

    with pytest.raises(SmtpConfigError, match="smtp_port"):
        load_smtp_config(config_path)


def test_send_alert_email_uses_starttls_for_standard_smtp_port(tmp_path):
    config_path = tmp_path / "smtp.conf"
    config_path.write_text(
        "host smtp.example.com\nport 587\nuser server\npassword secret\n",
        encoding="utf-8",
    )
    runtime = SimpleNamespace(smtp_config_path=config_path)
    smtp_instance = MagicMock()

    with (
        patch("simple_safer_server.modules.alerts.smtp_mailer.ssl.create_default_context") as context,
        patch("simple_safer_server.modules.alerts.smtp_mailer.smtplib.SMTP") as smtp_class,
    ):
        smtp_class.return_value.__enter__.return_value = smtp_instance
        context.return_value = "tls-context"

        SmtpAlertMailer(runtime).send_alert_email(
            email_address="admin@example.com",
            from_address="server@example.com",
            subject="Backup failed",
            message="message",
        )

    smtp_class.assert_called_once_with("smtp.example.com", 587, timeout=30)
    smtp_instance.starttls.assert_called_once_with(context="tls-context")
    smtp_instance.login.assert_called_once_with("server", "secret")
    sent_message = smtp_instance.send_message.call_args.args[0]
    assert sent_message["Subject"] == "Backup failed"
    assert sent_message["From"] == "server@example.com"
    assert sent_message["To"] == "admin@example.com"


def test_send_alert_email_uses_smtp_ssl_for_port_465(tmp_path):
    config_path = tmp_path / "smtp.conf"
    config_path.write_text(
        "host smtp.example.com\nport 465\nuser server\npassword secret\n",
        encoding="utf-8",
    )
    runtime = SimpleNamespace(smtp_config_path=config_path)
    smtp_instance = MagicMock()

    with (
        patch("simple_safer_server.modules.alerts.smtp_mailer.ssl.create_default_context") as context,
        patch("simple_safer_server.modules.alerts.smtp_mailer.smtplib.SMTP_SSL") as smtp_class,
    ):
        smtp_class.return_value.__enter__.return_value = smtp_instance
        context.return_value = "tls-context"

        SmtpAlertMailer(runtime).send_alert_email(
            email_address="admin@example.com",
            from_address="server@example.com",
            subject="Backup failed",
            message="message",
        )

    smtp_class.assert_called_once_with(
        "smtp.example.com",
        465,
        timeout=30,
        context="tls-context",
    )
    smtp_instance.starttls.assert_not_called()
    smtp_instance.login.assert_called_once_with("server", "secret")
