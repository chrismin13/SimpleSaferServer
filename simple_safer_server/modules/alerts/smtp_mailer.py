from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any

SMTP_TIMEOUT_SECONDS = 30


class SmtpConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class SmtpConfig:
    server: str
    port: int
    username: str
    password: str


def read_smtp_config(path: Path) -> dict[str, str]:
    """Read the SSS-owned SMTP config file."""
    config: dict[str, str] = {}
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return config

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("host "):
            config["smtp_server"] = line.split(" ", 1)[1]
        elif line.startswith("port "):
            config["smtp_port"] = line.split(" ", 1)[1]
        elif line.startswith("from "):
            config["from_address"] = line.split(" ", 1)[1]
        elif line.startswith("user "):
            config["smtp_username"] = line.split(" ", 1)[1]
        elif line.startswith("password "):
            config["smtp_password"] = line.split(" ", 1)[1]

    return config


def load_smtp_config(path: Path) -> SmtpConfig:
    config = read_smtp_config(path)
    missing = [
        key
        for key in ("smtp_server", "smtp_port", "smtp_username", "smtp_password")
        if not config.get(key)
    ]
    if missing:
        raise SmtpConfigError("SMTP config is missing: {}".format(", ".join(missing)))

    port_text = config["smtp_port"].strip()
    if not port_text.isdigit() or not 1 <= int(port_text) <= 65535:
        raise SmtpConfigError("SMTP port must be between 1 and 65535.")

    return SmtpConfig(
        server=config["smtp_server"].strip(),
        port=int(port_text),
        username=config["smtp_username"].strip(),
        password=config["smtp_password"],
    )


def runtime_smtp_config_path(runtime: Any) -> Path:
    return Path(runtime.smtp_config_path)


def read_runtime_smtp_config(runtime: Any) -> dict[str, str]:
    return read_smtp_config(runtime_smtp_config_path(runtime))


def load_runtime_smtp_config(runtime: Any) -> SmtpConfig:
    return load_smtp_config(runtime_smtp_config_path(runtime))


class SmtpAlertMailer:
    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    def send_alert_email(
        self,
        *,
        email_address: str,
        from_address: str,
        subject: str,
        message: str,
    ) -> None:
        smtp_config = load_runtime_smtp_config(self._runtime)
        email = EmailMessage()
        email["Subject"] = subject
        email["From"] = from_address
        email["To"] = email_address
        email.set_content(message)

        context = ssl.create_default_context()
        if smtp_config.port == 465:
            with smtplib.SMTP_SSL(
                smtp_config.server,
                smtp_config.port,
                timeout=SMTP_TIMEOUT_SECONDS,
                context=context,
            ) as smtp:
                smtp.login(smtp_config.username, smtp_config.password)
                smtp.send_message(email)
            return

        with smtplib.SMTP(
            smtp_config.server,
            smtp_config.port,
            timeout=SMTP_TIMEOUT_SECONDS,
        ) as smtp:
            smtp.starttls(context=context)
            smtp.login(smtp_config.username, smtp_config.password)
            smtp.send_message(email)
