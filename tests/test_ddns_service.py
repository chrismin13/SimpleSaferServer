import logging
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from simple_safer_server.services.ddns_service import DdnsService


class FakeConfigManager:
    def __init__(self):
        self.values = {}
        self.secrets = {}

    def get_value(self, section, key, default=None):
        return self.values.get((section, key), default)

    def set_value(self, section, key, value):
        self.values[(section, key)] = value

    def get_secret(self, key, default=None):
        return self.secrets.get(key, default)

    def store_secret(self, key, value):
        self.secrets[key] = value


class FakeTask:
    def __init__(self):
        self.next_run = "soon"
        self.starts = 0

    def start(self):
        self.starts += 1


class FakeTaskService:
    def __init__(self, task=None):
        self.task = task

    def get_task(self, name):
        if name == "DDNS Update":
            return self.task
        return None


class DdnsServiceTests(unittest.TestCase):
    def make_service(self, config=None, task=None):
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        runtime = types.SimpleNamespace(
            data_dir=Path(temp_dir.name),
            volatile_dir=Path(temp_dir.name) / "run",
        )
        config_manager = config or FakeConfigManager()
        task_service = FakeTaskService(task=task)
        service = DdnsService(runtime, config_manager, task_service, logging.getLogger("test"))
        return service, config_manager, task_service

    def test_config_payload_exposes_provider_tokens_for_admin_editing(self):
        task = FakeTask()
        config = FakeConfigManager()
        config.values.update(
            {
                ("ddns", "duckdns_enabled"): "true",
                ("ddns", "duckdns_domain"): "home",
                ("ddns", "cloudflare_enabled"): "true",
                ("ddns", "cloudflare_zone"): "zone-123",
                ("ddns", "cloudflare_record"): "server.example.com",
                ("ddns", "cloudflare_proxy"): "true",
            }
        )
        config.secrets.update({"duckdns_token": "duck-token", "cloudflare_token": "cf-token"})
        service, _config, _task_service = self.make_service(config=config, task=task)

        payload = service.get_config_payload()

        self.assertEqual(payload["config"]["duckdns"]["token"], "duck-token")
        self.assertEqual(payload["config"]["cloudflare"]["token"], "cf-token")
        self.assertEqual(payload["next_run"], "soon")

    def test_save_config_requires_duckdns_token_when_enabled(self):
        service, _config, _task_service = self.make_service()

        with self.assertRaisesRegex(ValueError, "DuckDNS token is required"):
            service.save_config({"duckdns": {"enabled": True, "domain": "home", "token": ""}})

    def test_save_config_persists_values_and_triggers_sync(self):
        task = FakeTask()
        service, config, _task_service = self.make_service(task=task)

        message = service.save_config(
            {
                "cloudflare": {
                    "enabled": True,
                    "zone": "zone-123",
                    "record": "server.example.com",
                    "token": "cf-token",
                    "proxy": True,
                }
            }
        )

        self.assertEqual(message, "DDNS configuration saved and update triggered.")
        self.assertEqual(config.values[("ddns", "cloudflare_record")], "server.example.com")
        self.assertEqual(config.values[("ddns", "cloudflare_proxy")], "true")
        self.assertEqual(config.secrets["cloudflare_token"], "cf-token")
        self.assertEqual(task.starts, 1)

    def test_run_manual_reports_missing_task(self):
        service, _config, _task_service = self.make_service()

        with self.assertRaisesRegex(LookupError, "DDNS Update task not found"):
            service.run_manual()


if __name__ == "__main__":
    unittest.main()
