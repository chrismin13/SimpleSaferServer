# pyright: reportAttributeAccessIssue=false
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class FakeFernet:
    @staticmethod
    def generate_key():
        return b"test-key"

    def __init__(self, key):
        self.key = key

    def encrypt(self, value):
        return value

    def decrypt(self, value):
        return value


def create_config_manager():
    cryptography_module = types.ModuleType("cryptography")
    fernet_module = types.ModuleType("cryptography.fernet")
    fernet_module.Fernet = FakeFernet

    temp_dir = tempfile.TemporaryDirectory()
    runtime = types.SimpleNamespace(
        config_dir=Path(temp_dir.name) / "config",
        default_mount_point="/media/backup",
    )

    module_patch = patch.dict(
        "sys.modules",
        {
            "cryptography": cryptography_module,
            "cryptography.fernet": fernet_module,
        },
    )
    module_patch.start()
    try:
        from simple_safer_server.services.config_manager import ConfigManager

        manager = ConfigManager(runtime=runtime)
    finally:
        module_patch.stop()
    manager._test_temp_dir = temp_dir
    return manager


class ConfigManagerDefaultsTests(unittest.TestCase):
    def test_cloudflare_proxy_defaults_to_dns_only(self):
        manager = create_config_manager()

        # Most DDNS users point records at home networks where non-HTTP
        # services need direct DNS, so the generated config must stay DNS-only.
        self.assertEqual(manager.get_value("ddns", "cloudflare_proxy"), "false")

    def test_apt_update_defaults_do_not_claim_system_ownership(self):
        manager = create_config_manager()

        self.assertEqual(manager.get_value("apt_updates", "managed"), "false")
        self.assertEqual(manager.get_value("apt_updates", "autoclean_interval"), "7")

    def test_alert_ids_stay_monotonic_after_retention_trim(self):
        manager = create_config_manager()

        manager.alerts_path.write_text(
            "[{}]".format(
                ",".join(
                    f'{{"id": {alert_id}, "title": "old", "read": false}}'
                    for alert_id in range(500, 1500)
                )
            )
        )

        self.assertTrue(manager.log_alert("Newest", "message"))
        alerts = manager.get_alerts()
        alert_ids = [alert["id"] for alert in alerts]

        self.assertEqual(len(alerts), 1000)
        self.assertEqual(max(alert_ids), 1500)
        self.assertEqual(sorted(alert_ids), list(range(501, 1501)))


if __name__ == "__main__":
    unittest.main()
