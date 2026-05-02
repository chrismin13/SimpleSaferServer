import json
import unittest
from subprocess import TimeoutExpired
from types import SimpleNamespace
from unittest.mock import patch

from simple_safer_server.services import drive_health


class DriveHealthTests(unittest.TestCase):
    @patch(
        "simple_safer_server.services.drive_health.get_smartctl_json_support",
        return_value=(False, drive_health.SMARTCTL_JSON_UPGRADE_MESSAGE),
    )
    def test_get_smart_attributes_keeps_json_unsupported_flow(self, _mock_json_support):
        runtime = SimpleNamespace(is_fake=False)

        attrs, missing, error = drive_health.get_smart_attributes(
            config_manager=None,
            system_utils=None,
            device="/dev/sdb",
            runtime=runtime,
        )

        self.assertIsNone(attrs)
        self.assertIsNone(missing)
        self.assertEqual(error, drive_health.SMARTCTL_JSON_UPGRADE_MESSAGE)

    @patch(
        "simple_safer_server.services.drive_health.get_smartctl_json_support",
        return_value=(True, None),
    )
    @patch(
        "simple_safer_server.services.drive_health.drive_health_command_adapter.smartctl_attributes"
    )
    def test_get_smart_attributes_treats_json_error_response_as_failure(
        self, mock_run, _mock_json_support
    ):
        runtime = SimpleNamespace(is_fake=False)
        mock_run.return_value = SimpleNamespace(
            returncode=2,
            stdout=json.dumps(
                {
                    "smartctl": {
                        "messages": [
                            {
                                "string": "Read Device Identity failed: scsi error unsupported scsi opcode"
                            }
                        ]
                    }
                }
            ),
            stderr="",
        )

        attrs, missing, error = drive_health.get_smart_attributes(
            config_manager=None,
            system_utils=None,
            device="/dev/sdb",
            runtime=runtime,
        )

        self.assertIsNone(attrs)
        self.assertIsNone(missing)
        self.assertIn("Read Device Identity failed", error)

    @patch(
        "simple_safer_server.services.drive_health.get_smartctl_json_support",
        return_value=(True, None),
    )
    @patch(
        "simple_safer_server.services.drive_health.drive_health_command_adapter.smartctl_attributes"
    )
    def test_get_smart_attributes_accepts_nonzero_exit_when_attributes_are_present(
        self, mock_run, _mock_json_support
    ):
        runtime = SimpleNamespace(is_fake=False)
        mock_run.return_value = SimpleNamespace(
            returncode=4,
            stdout=json.dumps(
                {
                    "ata_smart_attributes": {
                        "table": [
                            {"id": 194, "raw": {"value": "34"}},
                            {"id": 5, "raw": {"value": "2"}},
                        ]
                    }
                }
            ),
            stderr="SMART status check returned DISK FAILING",
        )

        attrs, missing, error = drive_health.get_smart_attributes(
            config_manager=None,
            system_utils=None,
            device="/dev/sdb",
            runtime=runtime,
        )

        self.assertIsNotNone(attrs)
        self.assertIsNone(error)
        self.assertEqual(attrs["smart_194_raw"], 34.0)
        self.assertEqual(attrs["smart_5_raw"], 2.0)
        self.assertIn("smart_1_raw", missing)

    @patch(
        "simple_safer_server.services.drive_health.get_smartctl_json_support",
        return_value=(True, None),
    )
    @patch(
        "simple_safer_server.services.drive_health.drive_health_command_adapter.smartctl_attributes"
    )
    def test_get_smart_attributes_preserves_parse_failure_when_json_supported(
        self, mock_run, _mock_json_support
    ):
        runtime = SimpleNamespace(is_fake=False)
        mock_run.return_value = SimpleNamespace(
            returncode=2,
            stdout=(
                "/dev/sda: Unknown USB bridge [0x1058:0x25ee (0x4009)]\n"
                "Please specify device type with the -d option."
            ),
            stderr="",
        )

        attrs, missing, error = drive_health.get_smart_attributes(
            config_manager=None,
            system_utils=None,
            device="/dev/sdb",
            runtime=runtime,
        )

        self.assertIsNone(attrs)
        self.assertIsNone(missing)
        self.assertIn("Unknown USB bridge", error)
        self.assertNotEqual(error, drive_health.SMARTCTL_JSON_UPGRADE_MESSAGE)

    @patch(
        "simple_safer_server.services.drive_health.drive_health_command_adapter.send_email",
        side_effect=TimeoutExpired(cmd=["msmtp"], timeout=30),
    )
    def test_log_and_email_alert_treats_email_timeout_as_warning(self, _mock_send_email):
        config_manager = SimpleNamespace(
            log_alert=lambda *args, **kwargs: None,
            get_value=lambda section, key, default="": {
                ("backup", "email_address"): "admin@example.com",
                ("backup", "from_address"): "server@example.com",
            }.get((section, key), default),
        )
        runtime = SimpleNamespace(is_fake=False)

        drive_health._log_and_email_alert(
            config_manager,
            runtime,
            "Drive health",
            "message",
            alert_type="warning",
            source="drive_health",
        )


if __name__ == "__main__":
    unittest.main()
