import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import types
import unittest
from unittest.mock import patch

# The script imports the full app runtime for main(); these unit tests only need
# the Cloudflare helpers and should not require optional app dependencies.
original_config_manager = sys.modules.get("config_manager")
original_runtime = sys.modules.get("runtime")

try:
    fake_config_manager = types.ModuleType("config_manager")
    fake_config_manager.ConfigManager = object
    sys.modules["config_manager"] = fake_config_manager

    fake_runtime = types.ModuleType("runtime")
    fake_runtime.get_runtime = lambda: None
    sys.modules["runtime"] = fake_runtime

    from scripts import ddns_update
finally:
    if original_config_manager is None:
        sys.modules.pop("config_manager", None)
    else:
        sys.modules["config_manager"] = original_config_manager

    if original_runtime is None:
        sys.modules.pop("runtime", None)
    else:
        sys.modules["runtime"] = original_runtime


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class CloudflareDdnsTests(unittest.TestCase):
    def run_main_with_config(
        self,
        values,
        secrets=None,
        public_ip="203.0.113.10",
        duckdns_result=(True, "OK"),
        cloudflare_result=(True, "Updated successfully"),
        initial_status=None,
    ):
        secrets = secrets or {}
        config_instances = []

        class FakeConfigManager:
            def __init__(self, runtime):
                self.runtime = runtime
                self.alerts = []
                config_instances.append(self)

            def get_value(self, section, key, default=None):
                return values.get((section, key), default)

            def get_secret(self, key, default=None):
                return secrets.get(key, default)

            def log_alert(self, *args, **kwargs):
                self.alerts.append((args, kwargs))

        with TemporaryDirectory() as temp_dir:
            runtime = types.SimpleNamespace(data_dir=Path(temp_dir))
            if initial_status is not None:
                # Seed the status file exactly like a prior scheduled run would
                # leave it, because alert de-dupe depends on persisted messages.
                (runtime.data_dir / "ddns_status.json").write_text(json.dumps(initial_status))
            with patch("scripts.ddns_update.get_runtime", return_value=runtime), patch(
                "scripts.ddns_update.ConfigManager", FakeConfigManager
            ), patch("scripts.ddns_update.get_public_ip", return_value=public_ip), patch(
                "scripts.ddns_update.update_duckdns", return_value=duckdns_result
            ), patch(
                "scripts.ddns_update.update_cloudflare", return_value=cloudflare_result
            ):
                exit_code = ddns_update.main()

            status_file = runtime.data_dir / "ddns_status.json"
            status_data = json.loads(status_file.read_text()) if status_file.exists() else None

        return exit_code, status_data, config_instances[0]

    def test_get_cloudflare_record_returns_proxy_state(self):
        payload = {
            "success": True,
            "result": [
                {
                    "id": "record-123",
                    "content": "203.0.113.10",
                    "proxied": True,
                }
            ],
        }

        with patch("scripts.ddns_update.urllib.request.urlopen", return_value=FakeResponse(payload)):
            self.assertEqual(
                ddns_update.get_cloudflare_record("zone-123", "token", "server.example.com"),
                ("record-123", "203.0.113.10", True),
            )

    def test_update_cloudflare_skips_when_ip_and_proxy_state_match(self):
        with patch(
            "scripts.ddns_update.get_cloudflare_record",
            return_value=("record-123", "203.0.113.10", True),
        ), patch("scripts.ddns_update.urllib.request.urlopen") as mock_urlopen:
            success, message = ddns_update.update_cloudflare(
                "zone-123",
                "token",
                "server.example.com",
                "203.0.113.10",
                "true",
            )

        self.assertTrue(success)
        self.assertEqual(message, "Record already current.")
        mock_urlopen.assert_not_called()

    def test_update_cloudflare_applies_proxy_change_when_ip_matches(self):
        captured_requests = []

        def fake_urlopen(request, timeout):
            # Keep the request so the test can prove the proxy-only change reaches Cloudflare.
            captured_requests.append(request)
            return FakeResponse({"success": True})

        with patch(
            "scripts.ddns_update.get_cloudflare_record",
            return_value=("record-123", "203.0.113.10", False),
        ), patch("scripts.ddns_update.urllib.request.urlopen", side_effect=fake_urlopen):
            success, message = ddns_update.update_cloudflare(
                "zone-123",
                "token",
                "server.example.com",
                "203.0.113.10",
                "true",
            )

        self.assertTrue(success)
        self.assertEqual(message, "Updated successfully")
        self.assertEqual(len(captured_requests), 1)
        self.assertEqual(captured_requests[0].get_method(), "PUT")
        self.assertEqual(
            json.loads(captured_requests[0].data.decode("utf-8")),
            {
                "type": "A",
                "name": "server.example.com",
                "content": "203.0.113.10",
                "proxied": True,
                "ttl": 1,
            },
        )

    def test_main_returns_failure_after_writing_duckdns_error_status(self):
        exit_code, status_data, config = self.run_main_with_config(
            {
                ("ddns", "duckdns_enabled"): "true",
                ("ddns", "duckdns_domain"): "home",
                ("ddns", "cloudflare_enabled"): "false",
            },
            secrets={"duckdns_token": "token"},
            duckdns_result=(False, "API returned: KO"),
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(status_data["duckdns"]["status"], "Error")
        self.assertEqual(status_data["duckdns"]["message"], "API returned: KO")
        self.assertEqual(len(config.alerts), 1)

    def test_main_alerts_when_duckdns_error_message_changes(self):
        exit_code, status_data, config = self.run_main_with_config(
            {
                ("ddns", "duckdns_enabled"): "true",
                ("ddns", "duckdns_domain"): "home",
                ("ddns", "cloudflare_enabled"): "false",
            },
            secrets={"duckdns_token": "token"},
            duckdns_result=(False, "API returned: KO"),
            initial_status={"duckdns": {"status": "Error", "message": "API returned: BAD"}},
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(status_data["duckdns"]["message"], "API returned: KO")
        self.assertEqual(len(config.alerts), 1)

    def test_main_suppresses_repeated_duckdns_error_message(self):
        _exit_code, status_data, config = self.run_main_with_config(
            {
                ("ddns", "duckdns_enabled"): "true",
                ("ddns", "duckdns_domain"): "home",
                ("ddns", "cloudflare_enabled"): "false",
            },
            secrets={"duckdns_token": "token"},
            duckdns_result=(False, "API returned: KO"),
            initial_status={"duckdns": {"status": "Error", "message": "API returned: KO"}},
        )

        self.assertEqual(status_data["duckdns"]["message"], "API returned: KO")
        self.assertEqual(config.alerts, [])

    def test_main_alerts_when_cloudflare_error_message_changes(self):
        exit_code, status_data, config = self.run_main_with_config(
            {
                ("ddns", "duckdns_enabled"): "false",
                ("ddns", "cloudflare_enabled"): "true",
                ("ddns", "cloudflare_zone"): "zone-123",
                ("ddns", "cloudflare_record"): "server.example.com",
            },
            secrets={"cloudflare_token": "token"},
            cloudflare_result=(False, "Record does not exist."),
            initial_status={"cloudflare": {"status": "Error", "message": "API returned failure"}},
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(status_data["cloudflare"]["message"], "Record does not exist.")
        self.assertEqual(len(config.alerts), 1)

    def test_main_suppresses_repeated_cloudflare_error_message(self):
        _exit_code, status_data, config = self.run_main_with_config(
            {
                ("ddns", "duckdns_enabled"): "false",
                ("ddns", "cloudflare_enabled"): "true",
                ("ddns", "cloudflare_zone"): "zone-123",
                ("ddns", "cloudflare_record"): "server.example.com",
            },
            secrets={"cloudflare_token": "token"},
            cloudflare_result=(False, "Record does not exist."),
            initial_status={"cloudflare": {"status": "Error", "message": "Record does not exist."}},
        )

        self.assertEqual(status_data["cloudflare"]["message"], "Record does not exist.")
        self.assertEqual(config.alerts, [])

    def test_main_returns_failure_after_writing_missing_config_status(self):
        exit_code, status_data, _config = self.run_main_with_config(
            {
                ("ddns", "duckdns_enabled"): "false",
                ("ddns", "cloudflare_enabled"): "true",
                ("ddns", "cloudflare_zone"): "zone-123",
                ("ddns", "cloudflare_record"): "server.example.com",
            },
            secrets={},
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(status_data["cloudflare"]["status"], "Configuration Missing")
        self.assertEqual(status_data["cloudflare"]["message"], "Zone, Record, or Token is missing.")

    def test_main_returns_failure_when_cloudflare_requires_missing_public_ip(self):
        exit_code, status_data, _config = self.run_main_with_config(
            {
                ("ddns", "duckdns_enabled"): "false",
                ("ddns", "cloudflare_enabled"): "true",
                ("ddns", "cloudflare_zone"): "zone-123",
                ("ddns", "cloudflare_record"): "server.example.com",
            },
            secrets={"cloudflare_token": "token"},
            public_ip=None,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(status_data["cloudflare"]["status"], "Error")
        self.assertEqual(
            status_data["cloudflare"]["message"],
            "Failed to fetch public IP required for Cloudflare.",
        )

    def test_main_returns_success_when_enabled_providers_succeed(self):
        exit_code, status_data, _config = self.run_main_with_config(
            {
                ("ddns", "duckdns_enabled"): "true",
                ("ddns", "duckdns_domain"): "home",
                ("ddns", "cloudflare_enabled"): "true",
                ("ddns", "cloudflare_zone"): "zone-123",
                ("ddns", "cloudflare_record"): "server.example.com",
            },
            secrets={"duckdns_token": "token", "cloudflare_token": "token"},
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(status_data["duckdns"]["status"], "Success")
        self.assertEqual(status_data["cloudflare"]["status"], "Success")


if __name__ == "__main__":
    unittest.main()
