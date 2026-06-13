import json
import tempfile
import unittest
from pathlib import Path
from subprocess import TimeoutExpired
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
    def test_get_smart_attributes_handles_empty_smartctl_messages(
        self, mock_run, _mock_json_support
    ):
        runtime = SimpleNamespace(is_fake=False)
        mock_run.return_value = SimpleNamespace(
            returncode=2,
            stdout=json.dumps({"smartctl": {"messages": []}}),
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
        self.assertEqual(error, "smartctl could not retrieve SMART attributes")

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
    def test_log_and_email_alert_treats_email_timeout_as_warning(self, mock_send_email):
        config_manager = SimpleNamespace(
            log_alert=MagicMock(),
            get_value=lambda section, key, default="": {
                ("backup", "email_address"): "admin@example.com",
                ("backup", "from_address"): "server@example.com",
                ("system", "server_name"): "nas-01",
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

        config_manager.log_alert.assert_called_once_with(
            "Drive health",
            "message",
            alert_type="warning",
            source="drive_health",
        )
        mock_send_email.assert_called_once()
        self.assertIn("Subject: Drive health - nas-01", mock_send_email.call_args[0][2])

    def test_hdsentinel_state_uses_durable_data_dir_not_repo_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = SimpleNamespace(
                is_fake=False,
                repo_root=root / "app",
                data_dir=root / "var-lib",
            )

            self.assertEqual(
                drive_health.get_hdsentinel_state_path(runtime),
                root / "var-lib" / "hdsentinel_state.json",
            )

    @patch("simple_safer_server.services.drive_health._log_and_email_alert")
    @patch("simple_safer_server.services.drive_health.run_hdsentinel_health_monitor")
    @patch("simple_safer_server.services.drive_health.get_smart_attributes")
    @patch("simple_safer_server.services.drive_health.resolve_backup_parent_device")
    def test_scheduled_check_succeeds_without_alerts_when_smart_is_available(
        self,
        mock_resolve_device,
        mock_smart_attributes,
        mock_hdsentinel_monitor,
        mock_alert,
    ):
        config_manager = SimpleNamespace(
            get_value=lambda section, key, default=None: {
                ("backup", "mount_point"): "/media/backup",
            }.get((section, key), default)
        )
        system_utils = SimpleNamespace(
            is_mounted=lambda mount_point: mount_point == "/media/backup"
        )
        runtime = SimpleNamespace(is_fake=False, default_mount_point="/media/backup")
        smart = {"smart_194_raw": 31.0}
        hdsentinel_result = {
            "snapshot": {"available": True, "health_pct": 100},
            "alert_sent": False,
        }

        mock_resolve_device.return_value = ("/dev/sdb", "/dev/sdb1", None)
        mock_smart_attributes.return_value = (smart, [], None)
        mock_hdsentinel_monitor.return_value = hdsentinel_result

        result = drive_health.run_scheduled_drive_health_check(
            config_manager,
            system_utils,
            runtime=runtime,
        )

        self.assertEqual(result["device"], "/dev/sdb")
        self.assertEqual(result["smart"], smart)
        self.assertEqual(result["missing_attrs"], [])
        self.assertEqual(result["hdsentinel"], hdsentinel_result)
        mock_alert.assert_not_called()
        mock_hdsentinel_monitor.assert_called_once_with(
            config_manager, system_utils, runtime=runtime
        )

    @patch("simple_safer_server.services.drive_health._log_and_email_alert")
    @patch("simple_safer_server.services.drive_health.run_hdsentinel_health_monitor")
    @patch("simple_safer_server.services.drive_health.get_smart_attributes")
    @patch("simple_safer_server.services.drive_health.resolve_backup_parent_device")
    def test_scheduled_json_unsupported_fallback_requires_hdsentinel_health(
        self,
        mock_resolve_device,
        mock_smart_attributes,
        mock_hdsentinel_monitor,
        mock_alert,
    ):
        config_manager = SimpleNamespace(
            get_value=lambda section, key, default=None: {
                ("backup", "mount_point"): "/media/backup",
            }.get((section, key), default)
        )
        system_utils = SimpleNamespace(
            is_mounted=lambda mount_point: mount_point == "/media/backup"
        )
        runtime = SimpleNamespace(is_fake=False, default_mount_point="/media/backup")
        hdsentinel_result = {
            "snapshot": {"available": True, "health_pct": None},
            "alert_sent": False,
        }

        mock_resolve_device.return_value = ("/dev/sdb", "/dev/sdb1", None)
        mock_smart_attributes.return_value = (
            None,
            None,
            drive_health.SMARTCTL_JSON_UPGRADE_MESSAGE,
        )
        mock_hdsentinel_monitor.return_value = hdsentinel_result

        with self.assertRaises(RuntimeError) as exc:
            drive_health.run_scheduled_drive_health_check(
                config_manager,
                system_utils,
                runtime=runtime,
            )

        self.assertIn("smartctl", str(exc.exception))
        mock_alert.assert_called_once()
        mock_hdsentinel_monitor.assert_called_once_with(
            config_manager, system_utils, runtime=runtime
        )


if __name__ == "__main__":
    unittest.main()
