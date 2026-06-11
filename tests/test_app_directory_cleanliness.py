import os
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from simple_safer_server.services import drive_health
from simple_safer_server.services.system_updates import SystemUpdatesManager


class FakeConfigManager:
    def get_value(self, _section, _key, default=None):
        return default

    def set_value(self, _section, _key, _value):
        return None


class FakeSystemUpdatesCommandAdapter:
    def __init__(self):
        self.apt_periodic_content = ""

    def write_apt_periodic_config(self, temp_file):
        self.apt_periodic_content = temp_file.read()

    def pro_attach(self, pro_binary, attach_config_path):
        self.attach_config_path = attach_config_path
        return SimpleNamespace(returncode=0, stdout="", stderr="", args=[pro_binary])

    def pro_enable_livepatch(self, _pro_binary):
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def _git(repo: Path, *args: str):
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    )


def test_normal_app_state_writes_do_not_dirty_installed_git_checkout():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        app_dir = root / "app"
        data_dir = root / "var-lib"
        volatile_dir = root / "run"
        app_dir.mkdir()
        (app_dir / "tracked.txt").write_text("tracked\n", encoding="utf-8")
        _git(app_dir, "init")
        _git(app_dir, "config", "user.email", "admin@example.com")
        _git(app_dir, "config", "user.name", "Admin")
        _git(app_dir, "add", "tracked.txt")
        _git(app_dir, "commit", "-m", "initial")

        runtime = SimpleNamespace(
            mode="real",
            is_fake=False,
            repo_root=app_dir,
            data_dir=data_dir,
            volatile_dir=volatile_dir,
            config_dir=root / "etc",
            default_mount_point=str(root / "backup"),
        )
        command_adapter = FakeSystemUpdatesCommandAdapter()
        manager = SystemUpdatesManager(
            FakeConfigManager(),
            runtime=runtime,
            command_adapter=command_adapter,
        )

        drive_health.save_hdsentinel_state({"available": True}, runtime=runtime)
        manager._write_apt_periodic_config(
            {
                "update_package_lists": True,
                "unattended_upgrade": False,
                "autoclean_interval": 7,
            }
        )
        with patch.object(manager, "get_distribution_info", return_value={"id": "ubuntu"}):
            with patch.object(manager, "get_livepatch_status", return_value={"enabled": True}):
                with patch(
                    "simple_safer_server.services.system_updates.shutil.which",
                    return_value="/usr/bin/pro",
                ):
                    manager.setup_livepatch("secret-token")

        status = _git(app_dir, "status", "--porcelain").stdout

        assert status == ""
        assert (data_dir / "hdsentinel_state.json").exists()
        assert command_adapter.apt_periodic_content
        assert command_adapter.attach_config_path.parent == volatile_dir
        assert not command_adapter.attach_config_path.exists()


def test_gitignore_keeps_install_artifacts_ignored_without_hiding_known_state_files():
    repo_root = Path(__file__).resolve().parents[1]
    # CI can mount the checkout with a different owner than the test process.
    # safe.directory is only honored from protected config scopes, so use an
    # isolated global config instead of `git -c` to keep this focused on ignore rules.
    with tempfile.NamedTemporaryFile() as global_config:
        git_env = {**os.environ, "GIT_CONFIG_GLOBAL": global_config.name}
        subprocess.run(
            ["git", "config", "--global", "--add", "safe.directory", str(repo_root)],
            check=True,
            env=git_env,
        )

        ignored = subprocess.run(
            [
                "git",
                "check-ignore",
                ".venv/bin/python",
                "venv/bin/python",
                "simple_safer_server/__pycache__/module.pyc",
                "app.log",
                ".dev-data/config/config.conf",
            ],
            cwd=str(repo_root),
            check=False,
            capture_output=True,
            text=True,
            env=git_env,
        )
        not_ignored = subprocess.run(
            ["git", "check-ignore", "hdsentinel_state.json", "20auto-upgrades"],
            cwd=str(repo_root),
            check=False,
            capture_output=True,
            text=True,
            env=git_env,
        )

    assert ignored.returncode == 0
    assert not_ignored.returncode == 1
