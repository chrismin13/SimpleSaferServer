import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from simple_safer_server.services import runtime


class RuntimeHelpersTests(unittest.TestCase):
    def test_get_runtime_fake_mode_uses_repo_root_data_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module_path = Path(temp_dir) / "simple_safer_server" / "services" / "runtime.py"

            with patch.dict(os.environ, {"SSS_MODE": "fake"}, clear=True):
                with patch.object(runtime, "__file__", str(module_path)):
                    prev_runtime = runtime._runtime
                    prev_fake = runtime._fake_state
                    runtime._runtime = None
                    runtime._fake_state = None
                    try:
                        resolved_runtime = runtime.get_runtime()
                    finally:
                        runtime._runtime = prev_runtime
                        runtime._fake_state = prev_fake

        self.assertEqual(resolved_runtime.data_dir, Path(temp_dir) / ".dev-data")
        self.assertEqual(resolved_runtime.volatile_dir, Path(temp_dir) / ".dev-data" / "run")
        self.assertEqual(resolved_runtime.config_dir, Path(temp_dir) / ".dev-data" / "config")

    def test_resolve_fake_data_dir_prefers_railway_volume_over_default_data_path(self):
        repo_root = Path("/srv/simple-safer-server")

        # Railway service variables set SSS_DATA_DIR=/data, so this guards the
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
        repo_root = Path("/srv/simple-safer-server")

        with tempfile.TemporaryDirectory() as temp_dir:
            custom_data_dir = Path(temp_dir) / "custom-fake-data"

            with patch.dict(
                os.environ,
                {
                    "SSS_DATA_DIR": str(custom_data_dir),
                    "RAILWAY_VOLUME_MOUNT_PATH": "/var/lib/railway/volumes/app-data",
                },
                clear=True,
            ):
                self.assertEqual(
                    runtime.resolve_fake_data_dir(repo_root),
                    custom_data_dir.resolve(),
                )

    def test_resolve_volatile_dir_uses_run_for_real_mode_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                runtime.resolve_volatile_dir(Path("/opt/SimpleSaferServer"), is_fake=False),
                Path("/run/SimpleSaferServer"),
            )

    def test_get_runtime_real_mode_keeps_durable_data_outside_app_checkout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module_path = Path(temp_dir) / "simple_safer_server" / "services" / "runtime.py"

            with patch.dict(os.environ, {"SSS_MODE": "real"}, clear=True):
                with patch.object(runtime, "__file__", str(module_path)):
                    prev_runtime = runtime._runtime
                    prev_fake = runtime._fake_state
                    runtime._runtime = None
                    runtime._fake_state = None
                    try:
                        resolved_runtime = runtime.get_runtime()
                    finally:
                        runtime._runtime = prev_runtime
                        runtime._fake_state = prev_fake

        self.assertEqual(resolved_runtime.repo_root, Path(temp_dir))
        self.assertEqual(resolved_runtime.data_dir, Path("/var/lib/SimpleSaferServer"))
        self.assertEqual(resolved_runtime.volatile_dir, Path("/run/SimpleSaferServer"))

    def test_resolve_volatile_dir_accepts_explicit_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            configured = Path(temp_dir) / "volatile"
            with patch.dict(os.environ, {"SSS_VOLATILE_DIR": str(configured)}, clear=True):
                self.assertEqual(
                    runtime.resolve_volatile_dir(Path("/data"), is_fake=True),
                    configured.resolve(),
                )

    def test_load_or_create_text_secret_reuses_existing_file_contents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            secret_path = Path(temp_dir) / ".flask-secret-key"
            secret_path.write_text("persisted-secret")
            secret_path.chmod(0o644)

            self.assertEqual(runtime.load_or_create_text_secret(secret_path), "persisted-secret")
            self.assertEqual(secret_path.stat().st_mode & 0o777, 0o600)

    def test_load_or_create_text_secret_creates_new_secret_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            secret_path = Path(temp_dir) / ".flask-secret-key"

            first_secret = runtime.load_or_create_text_secret(secret_path)
            second_secret = runtime.load_or_create_text_secret(secret_path)

            self.assertTrue(first_secret)
            self.assertEqual(first_secret, second_secret)
            self.assertEqual(secret_path.read_text().strip(), first_secret)
            self.assertEqual(secret_path.stat().st_mode & 0o777, 0o600)

    def test_load_or_create_text_secret_reads_winner_after_race(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            secret_path = Path(temp_dir) / ".flask-secret-key"

            def fake_os_open(path, flags, mode):
                # Simulate another process creating the secret after our first
                # existence check but before our exclusive create runs.
                secret_path.write_text("winner-secret")
                secret_path.chmod(0o644)
                raise FileExistsError

            with patch("simple_safer_server.services.runtime.os.open", side_effect=fake_os_open):
                self.assertEqual(runtime.load_or_create_text_secret(secret_path), "winner-secret")

            self.assertEqual(secret_path.stat().st_mode & 0o777, 0o600)

    def test_load_or_create_text_secret_retries_until_race_winner_finishes_writing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            secret_path = Path(temp_dir) / ".flask-secret-key"

            with patch("simple_safer_server.services.runtime.os.open", side_effect=FileExistsError):
                with patch(
                    "simple_safer_server.services.runtime._read_persisted_text_secret",
                    side_effect=[None, None, "winner-secret"],
                ) as mock_read_secret:
                    with patch("simple_safer_server.services.runtime.time.sleep") as mock_sleep:
                        self.assertEqual(
                            runtime.load_or_create_text_secret(secret_path), "winner-secret"
                        )

            self.assertEqual(mock_read_secret.call_count, 3)
            self.assertEqual(mock_sleep.call_count, 1)
