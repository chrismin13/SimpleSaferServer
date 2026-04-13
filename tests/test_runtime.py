import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import runtime


class RuntimeHelpersTests(unittest.TestCase):
    def test_resolve_fake_data_dir_prefers_railway_volume_over_default_data_path(self):
        repo_root = Path("/tmp/simple-safer-server")

        # The repo pins SSS_DATA_DIR to /data for Railway, so this guards the
        # easy-to-forget case where the real volume gets mounted somewhere else.
        with patch.dict(
            os.environ,
            {
                "SSS_DATA_DIR": "/data",
                "RAILWAY_VOLUME_MOUNT_PATH": "/var/lib/railway/volumes/app-data",
            },
            clear=True,
        ):
            self.assertEqual(
                runtime.resolve_fake_data_dir(repo_root),
                Path("/var/lib/railway/volumes/app-data"),
            )

    def test_resolve_fake_data_dir_keeps_explicit_custom_path(self):
        repo_root = Path("/tmp/simple-safer-server")

        with patch.dict(
            os.environ,
            {
                "SSS_DATA_DIR": "/srv/simple-safer-server",
                "RAILWAY_VOLUME_MOUNT_PATH": "/var/lib/railway/volumes/app-data",
            },
            clear=True,
        ):
            self.assertEqual(
                runtime.resolve_fake_data_dir(repo_root),
                Path("/srv/simple-safer-server"),
            )

    def test_load_or_create_text_secret_reuses_existing_file_contents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            secret_path = Path(temp_dir) / ".flask-secret-key"
            secret_path.write_text("persisted-secret")

            self.assertEqual(runtime.load_or_create_text_secret(secret_path), "persisted-secret")

    def test_load_or_create_text_secret_creates_new_secret_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            secret_path = Path(temp_dir) / ".flask-secret-key"

            first_secret = runtime.load_or_create_text_secret(secret_path)
            second_secret = runtime.load_or_create_text_secret(secret_path)

            self.assertTrue(first_secret)
            self.assertEqual(first_secret, second_secret)
            self.assertEqual(secret_path.read_text().strip(), first_secret)
