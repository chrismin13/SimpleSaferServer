import tempfile
import types
import unittest
from pathlib import Path

from simple_safer_server.services.rclone_filters import (
    build_rclone_filter_text,
    read_rclone_pattern_texts,
    write_rclone_pattern_texts,
)
from simple_safer_server.web.problems import ValidationProblem


class RcloneFilterTests(unittest.TestCase):
    def test_build_filter_text_uses_excludes_then_includes_then_final_exclude(self):
        text = build_rclone_filter_text(
            exclude_patterns="*.tmp\n# ignored\n.cache/**\n",
            include_patterns="Documents/**\nPhotos/**/*.jpg\n",
        )

        self.assertEqual(
            text,
            "- *.tmp\n- .cache/**\n+ Documents/**\n+ Photos/**/*.jpg\n- **\n",
        )

    def test_build_filter_text_only_excludes_without_final_exclude(self):
        text = build_rclone_filter_text(
            exclude_patterns="*.tmp\n",
            include_patterns="",
        )

        self.assertEqual(text, "- *.tmp\n")

    def test_rejects_raw_filter_rules_in_pattern_fields(self):
        with self.assertRaisesRegex(ValidationProblem, "plain rclone patterns"):
            build_rclone_filter_text(exclude_patterns="- secret/**", include_patterns="")

    def test_pattern_files_are_private_and_round_trip_admin_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = types.SimpleNamespace(config_dir=Path(temp_dir))

            write_rclone_pattern_texts(
                runtime,
                exclude_patterns="*.tmp\n",
                include_patterns="Documents/**\n",
            )
            include_path = runtime.config_dir / "rclone_include_patterns.txt"
            exclude_path = runtime.config_dir / "rclone_exclude_patterns.txt"

            self.assertEqual(include_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(exclude_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                read_rclone_pattern_texts(runtime),
                {
                    "rclone_include_patterns": "Documents/**\n",
                    "rclone_exclude_patterns": "*.tmp\n",
                },
            )


if __name__ == "__main__":
    unittest.main()
