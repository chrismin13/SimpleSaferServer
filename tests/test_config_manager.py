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


class ConfigManagerDefaultsTests(unittest.TestCase):
    def test_cloudflare_proxy_defaults_to_dns_only(self):
        cryptography_module = types.ModuleType("cryptography")
        fernet_module = types.ModuleType("cryptography.fernet")
        fernet_module.Fernet = FakeFernet

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = types.SimpleNamespace(
                config_dir=Path(temp_dir) / "config",
                default_mount_point="/media/backup",
            )

            with patch.dict(
                "sys.modules",
                {
                    "cryptography": cryptography_module,
                    "cryptography.fernet": fernet_module,
                },
            ):
                from config_manager import ConfigManager

                manager = ConfigManager(runtime=runtime)

            # Most DDNS users point records at home networks where non-HTTP
            # services need direct DNS, so the generated config must stay DNS-only.
            self.assertEqual(manager.get_value("ddns", "cloudflare_proxy"), "false")

    def test_apt_update_defaults_do_not_claim_system_ownership(self):
        cryptography_module = types.ModuleType("cryptography")
        fernet_module = types.ModuleType("cryptography.fernet")
        fernet_module.Fernet = FakeFernet

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = types.SimpleNamespace(
                config_dir=Path(temp_dir) / "config",
                default_mount_point="/media/backup",
            )

            with patch.dict(
                "sys.modules",
                {
                    "cryptography": cryptography_module,
                    "cryptography.fernet": fernet_module,
                },
            ):
                from config_manager import ConfigManager

                manager = ConfigManager(runtime=runtime)

            self.assertEqual(manager.get_value("apt_updates", "managed"), "false")
            self.assertEqual(manager.get_value("apt_updates", "autoclean_interval"), "7")


if __name__ == "__main__":
    unittest.main()
