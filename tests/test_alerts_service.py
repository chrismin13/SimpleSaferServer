import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from simple_safer_server.core.privileged_client import PrivilegedActionClientError
from simple_safer_server.modules.alerts.service import AlertsService
from simple_safer_server.web.problems import ForbiddenProblem, OperationProblem, ValidationProblem


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
    pass


class FakePrivilegedActions:
    def __init__(self):
        self.calls = []
        self.error = None

    def run(self, action, payload):
        self.calls.append((action, payload))
        if self.error is not None:
            raise self.error
        return types.SimpleNamespace(action=action, data={"path": "/managed/smtp.conf"})


class AlertsServiceTests(unittest.TestCase):
    def make_service(self, is_fake=True):
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        runtime = types.SimpleNamespace(
            is_fake=is_fake,
            smtp_config_path=Path(temp_dir.name) / "smtp.conf",
        )
        config = FakeConfigManager()
        system_utils = FakeSystemUtils()
        privileged_actions = FakePrivilegedActions()
        service = AlertsService(runtime, config, system_utils, privileged_actions)
        return service, config, system_utils, runtime, privileged_actions

    def test_generate_test_alerts_is_fake_mode_only(self):
        service, config, _system_utils, _runtime, _privileged_actions = self.make_service(
            is_fake=True
        )

        result = service.generate_test_alerts()

        self.assertIsNone(result)
        self.assertEqual(len(config.alerts), 4)
        self.assertGreater(len(config.alerts[-1][1]), 2000)

    def test_generate_test_alerts_rejects_real_mode(self):
        service, _config, _system_utils, _runtime, _privileged_actions = self.make_service(
            is_fake=False
        )

        with self.assertRaisesRegex(ForbiddenProblem, "Not available in production mode"):
            service.generate_test_alerts()

    def test_email_config_exposes_existing_password_for_admin_editing(self):
        service, _config, _system_utils, runtime, _privileged_actions = self.make_service()
        runtime.smtp_config_path.write_text("host smtp.example\npassword secret\n")

        payload = service.get_email_config()

        self.assertTrue(payload.has_smtp_password)
        self.assertEqual(payload.config["smtp_password"], "secret")

    def test_save_email_config_reuses_existing_password(self):
        service, config, _system_utils, runtime, privileged_actions = self.make_service()
        runtime.smtp_config_path.write_text("password existing-secret\n")

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
        self.assertEqual(
            privileged_actions.calls,
            [
                (
                    "alerts.write-smtp-config",
                    {
                        "from_address": "server@example.com",
                        "smtp_server": "smtp.example.com",
                        "smtp_port": "587",
                        "smtp_username": "server",
                        "smtp_password": "existing-secret",
                    },
                )
            ],
        )

    def test_save_email_config_does_not_store_addresses_when_helper_fails(self):
        service, config, _system_utils, runtime, privileged_actions = self.make_service()
        runtime.smtp_config_path.write_text("password existing-secret\n")
        privileged_actions.error = PrivilegedActionClientError("helper failed", exit_code=2)

        with self.assertRaisesRegex(OperationProblem, "Failed to write SMTP configuration"):
            service.save_email_config(
                {
                    "email_address": "admin@example.com",
                    "from_address": "server@example.com",
                    "smtp_server": "smtp.example.com",
                    "smtp_port": "587",
                    "smtp_username": "server",
                }
            )

        self.assertNotIn(("backup", "email_address"), config.values)

    def test_save_email_config_rejects_non_numeric_smtp_port(self):
        service, _config, _system_utils, runtime, privileged_actions = self.make_service()
        runtime.smtp_config_path.write_text("password existing-secret\n")

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
        self.assertEqual(privileged_actions.calls, [])


if __name__ == "__main__":
    unittest.main()
