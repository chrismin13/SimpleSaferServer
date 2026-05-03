import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from simple_safer_server.services.alerts_service import AlertsService
from simple_safer_server.web.problems import ForbiddenProblem, ValidationProblem


class FakeConfigManager:
    def __init__(self):
        self.values = {}
        self.alerts = []

    def get_value(self, section, key, default=None):
        return self.values.get((section, key), default)

    def set_value(self, section, key, value):
        self.values[(section, key)] = value

    def log_alert(self, title, message, alert_type="info", source=None):
        self.alerts.append((title, message, alert_type, source))

    def get_alerts(self):
        return [{"id": 1, "title": "One"}]

    def mark_alert_read(self, alert_id):
        return alert_id == 1

    def clear_alerts(self):
        return True

    def mark_all_alerts_read(self):
        return True


class FakeSystemUtils:
    def __init__(self):
        self.msmtp_args = None

    def write_msmtp_config(self, from_address, server, port, username, password):
        self.msmtp_args = (from_address, server, port, username, password)
        return True


class AlertsServiceTests(unittest.TestCase):
    def make_service(self, is_fake=True):
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        runtime = types.SimpleNamespace(
            is_fake=is_fake,
            msmtp_config_path=Path(temp_dir.name) / "msmtprc",
        )
        config = FakeConfigManager()
        system_utils = FakeSystemUtils()
        service = AlertsService(runtime, config, system_utils)
        return service, config, system_utils, runtime

    def test_generate_test_alerts_is_fake_mode_only(self):
        service, config, _system_utils, _runtime = self.make_service(is_fake=True)

        result = service.generate_test_alerts()

        self.assertIsNone(result)
        self.assertEqual(len(config.alerts), 4)
        self.assertGreater(len(config.alerts[-1][1]), 2000)

    def test_generate_test_alerts_rejects_real_mode(self):
        service, _config, _system_utils, _runtime = self.make_service(is_fake=False)

        with self.assertRaisesRegex(ForbiddenProblem, "Not available in production mode"):
            service.generate_test_alerts()

    def test_email_config_exposes_existing_password_for_admin_editing(self):
        service, _config, _system_utils, runtime = self.make_service()
        runtime.msmtp_config_path.write_text("host smtp.example\npassword secret\n")

        payload = service.get_email_config()

        self.assertTrue(payload.has_smtp_password)
        self.assertEqual(payload.config["smtp_password"], "secret")

    def test_save_email_config_reuses_existing_password(self):
        service, config, system_utils, runtime = self.make_service()
        runtime.msmtp_config_path.write_text("password existing-secret\n")

        payload = service.save_email_config(
            {
                "email_address": "admin@example.com",
                "from_address": "server@example.com",
                "smtp_server": "smtp.example.com",
                "smtp_port": "587",
                "smtp_username": "server",
            }
        )

        self.assertIsNone(payload)
        self.assertEqual(config.values[("backup", "email_address")], "admin@example.com")
        self.assertIsNotNone(system_utils.msmtp_args)
        msmtp_args = system_utils.msmtp_args
        assert msmtp_args is not None
        self.assertEqual(msmtp_args[-1], "existing-secret")

    def test_save_email_config_rejects_non_numeric_smtp_port(self):
        service, _config, system_utils, runtime = self.make_service()
        runtime.msmtp_config_path.write_text("password existing-secret\n")

        with self.assertRaisesRegex(ValidationProblem, "SMTP port must be between 1 and 65535"):
            service.save_email_config(
                {
                    "email_address": "admin@example.com",
                    "from_address": "server@example.com",
                    "smtp_server": "smtp.example.com",
                    "smtp_port": "587abc",
                    "smtp_username": "server",
                }
            )
        self.assertIsNone(system_utils.msmtp_args)


if __name__ == "__main__":
    unittest.main()
