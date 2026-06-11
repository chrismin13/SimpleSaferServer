import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class InstallDevScriptTests(unittest.TestCase):
    def test_script_anchors_paths_to_repository_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_repo = Path(temp_dir) / "repo"
            fake_repo.mkdir()
            (fake_repo / "install_dev.sh").write_text((REPO_ROOT / "install_dev.sh").read_text())

            fake_bin = Path(temp_dir) / "bin"
            fake_bin.mkdir()
            fake_uv = fake_bin / "uv"
            fake_uv.write_text(
                textwrap.dedent(
                    f"""\
                    #!/bin/sh
                    printf '%s\n' "$PWD $*" >> "{temp_dir}/uv-args.log"
                    if [ "$1" = "run" ] && [ "$2" = "python" ]; then
                      printf '%s\n' 3.14.4
                    fi
                    exit 0
                    """
                )
            )
            fake_uv.chmod(0o755)

            env = {
                **os.environ,
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
            }
            result = subprocess.run(
                ["bash", str(fake_repo / "install_dev.sh")],
                cwd=temp_dir,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            uv_args = (Path(temp_dir) / "uv-args.log").read_text()
            self.assertIn(f"{fake_repo} sync --group dev", uv_args)
            self.assertIn(f"{fake_repo} run python -c", uv_args)
            self.assertIn("using Python 3.14.4", result.stdout)


if __name__ == "__main__":
    unittest.main()
