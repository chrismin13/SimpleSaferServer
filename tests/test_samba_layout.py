import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from simple_safer_server.services.samba_layout import (
    SSS_GLOBALS_INCLUDE_BEGIN,
    SSS_SHARES_INCLUDE_BEGIN,
    SSS_SHARES_INCLUDE_END,
    SambaLayoutError,
    SambaLayoutService,
)


class FakeSambaCommandAdapter:
    def __init__(self, *, validation_returncode=0):
        self.validation_returncode = validation_returncode
        self.validated_paths = []

    def validate_config(self, validator, candidate_path, cwd=None):
        self.validated_paths.append(Path(candidate_path))
        return SimpleNamespace(
            returncode=self.validation_returncode,
            stdout="",
            stderr="invalid include target" if self.validation_returncode else "",
        )


class SambaLayoutServiceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.runtime = SimpleNamespace(
            samba_dir=self.root / "samba",
            is_fake=True,
        )
        self.runtime.samba_dir.mkdir(parents=True)
        self.adapter = FakeSambaCommandAdapter()
        self.service = SambaLayoutService(runtime=self.runtime, command_adapter=self.adapter)

    def write_main_config(self, content):
        (self.runtime.samba_dir / "smb.conf").write_text(content, encoding="utf-8")

    def read_main_config(self):
        return (self.runtime.samba_dir / "smb.conf").read_text(encoding="utf-8")

    def test_creates_owned_files_and_places_includes_without_changing_unrelated_config(self):
        self.write_main_config(
            "\n".join(
                [
                    "# site note",
                    "[global]",
                    "   workgroup = WORKGROUP",
                    "   server string = Simple",
                    "",
                    "[media]",
                    "   path = /srv/media",
                    "",
                ]
            )
        )

        self.service.ensure_layout()

        content = self.read_main_config()
        self.assertIn("# site note\n[global]\n", content)
        self.assertIn("   server string = Simple\n", content)
        self.assertLess(content.index(SSS_GLOBALS_INCLUDE_BEGIN), content.index("[media]"))
        self.assertTrue(content.rstrip().endswith(SSS_SHARES_INCLUDE_END))
        self.assertEqual(len(self.adapter.validated_paths), 1)

        globals_content = (self.runtime.samba_dir / "simple_safer_server_globals.conf").read_text(
            encoding="utf-8"
        )
        self.assertIn("map to guest = never", globals_content)
        self.assertIn("disable netbios = no", globals_content)
        self.assertNotIn("[global]", globals_content)
        self.assertEqual(
            (self.runtime.samba_dir / "simple_safer_server_globals.conf").stat().st_mode & 0o777,
            0o644,
        )

        shares_content = (self.runtime.samba_dir / "simple_safer_server_shares.conf").read_text(
            encoding="utf-8"
        )
        self.assertIn("normal share changes should use the Web UI", shares_content)
        self.assertIn("unsupported manual directives may be overwritten", shares_content)
        self.assertEqual(
            (self.runtime.samba_dir / "simple_safer_server_shares.conf").stat().st_mode & 0o777,
            0o644,
        )

    def test_layout_helper_is_idempotent(self):
        self.write_main_config(
            "[global]\n   workgroup = WORKGROUP\n\n[media]\n   path = /srv/media\n"
        )

        self.service.ensure_layout()
        first_content = self.read_main_config()
        self.service.ensure_layout()

        self.assertEqual(self.read_main_config(), first_content)
        self.assertEqual(self.read_main_config().count(SSS_GLOBALS_INCLUDE_BEGIN), 1)
        self.assertEqual(self.read_main_config().count(SSS_SHARES_INCLUDE_BEGIN), 1)

    def test_malformed_marker_blocks_fail_closed(self):
        self.write_main_config(
            "\n".join(
                [
                    "[global]",
                    SSS_GLOBALS_INCLUDE_BEGIN,
                    "   include = /etc/samba/simple_safer_server_globals.conf",
                    "",
                    "[media]",
                    "   path = /srv/media",
                    "",
                ]
            )
        )

        with self.assertRaisesRegex(SambaLayoutError, "malformed"):
            self.service.ensure_layout()

    def test_validation_failure_rolls_back_all_layout_changes(self):
        self.write_main_config("[global]\n   workgroup = WORKGROUP\n")
        failing_service = SambaLayoutService(
            runtime=self.runtime,
            command_adapter=FakeSambaCommandAdapter(validation_returncode=1),
        )

        with self.assertRaisesRegex(SambaLayoutError, "validation failed"):
            failing_service.ensure_layout()

        self.assertEqual(self.read_main_config(), "[global]\n   workgroup = WORKGROUP\n")
        self.assertFalse((self.runtime.samba_dir / "simple_safer_server_globals.conf").exists())
        self.assertFalse((self.runtime.samba_dir / "simple_safer_server_shares.conf").exists())


if __name__ == "__main__":
    unittest.main()
