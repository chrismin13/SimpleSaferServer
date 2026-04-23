import json
import sys
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


if __name__ == "__main__":
    unittest.main()
