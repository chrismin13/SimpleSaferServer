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
            for filename in (
                "install_dev.sh",
                "requirements.txt",
                "requirements-dev.txt",
            ):
                (fake_repo / filename).write_text((REPO_ROOT / filename).read_text())

            fake_bin = Path(temp_dir) / "bin"
            fake_bin.mkdir()
            fake_python3 = fake_bin / "python3"
            venv_python = fake_repo / ".venv" / "bin" / "python"
            venv_python.parent.mkdir(parents=True, exist_ok=True)

            fake_python3.write_text(
                textwrap.dedent(
                    f"""\
                    #!/bin/sh
                    mkdir -p {venv_python.parent}
                    cat > {venv_python} <<'PY'
                    #!/bin/sh
                    if [ "$1" = "-c" ]; then
                      case "$2" in
                        *version_info*legacy*) printf '%s\\n' current ;;
                        *) printf '%s\\n' 3.13.0 ;;
                      esac
                      exit 0
                    fi
                    if [ "$1" = "-m" ] && [ "$2" = "pip" ]; then
                      shift 2
                      printf '%s\\n' "$@" >> "{temp_dir}/pip-args.log"
                      exit 0
                    fi
                    exit 1
                    PY
                    chmod +x {venv_python}
                    """
                )
            )
            fake_python3.chmod(0o755)

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
            pip_args = (Path(temp_dir) / "pip-args.log").read_text()
            self.assertIn(str(fake_repo / "requirements.txt"), pip_args)
            self.assertIn(str(fake_repo / "requirements-dev.txt"), pip_args)
            self.assertIn("using Python 3.13.0 and requirements.txt", result.stdout)


if __name__ == "__main__":
    unittest.main()
