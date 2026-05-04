import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from simple_safer_server.services.app_updates import AppUpdateError, AppUpdateManager


def make_runtime(root):
    return SimpleNamespace(
        is_fake=True,
        repo_root=root,
        data_dir=root,
        volatile_dir=root / "run",
    )


def git(repo, *args):
    return subprocess.run(
        ["git", *list(args)],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    )


class AppUpdateManagerTests(unittest.TestCase):
    def make_repo_pair(self):
        temp_dir = tempfile.TemporaryDirectory()
        root = Path(temp_dir.name)
        remote = root / "remote.git"
        clone = root / "clone"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
        subprocess.run(["git", "clone", str(remote), str(clone)], check=True, capture_output=True)
        git(clone, "config", "user.email", "admin@example.com")
        git(clone, "config", "user.name", "Admin")
        (clone / "file.txt").write_text("one\n", encoding="utf-8")
        git(clone, "add", "file.txt")
        git(clone, "commit", "-m", "initial")
        git(clone, "push", "-u", "origin", "master")
        return temp_dir, root, remote, clone

    def manager(self, root, clone, adapter=None):
        return AppUpdateManager(
            runtime=make_runtime(root),
            repo_path=clone,
            command_adapter=adapter,
        )

    def test_status_reports_branch_up_to_date_after_remote_check(self):
        temp_dir, root, _remote, clone = self.make_repo_pair()
        with temp_dir:
            status = self.manager(root, clone).get_status(fetch_remote=True)

        self.assertEqual(status["source_type"], "branch")
        self.assertEqual(status["source_name"], "master")
        self.assertEqual(status["status"], "up_to_date")
        self.assertFalse(status["can_update"])
        self.assertEqual(status["behind"], 0)

    def test_status_reports_branch_behind(self):
        temp_dir, root, _remote, clone = self.make_repo_pair()
        with temp_dir:
            other = root / "other"
            subprocess.run(
                ["git", "clone", str(root / "remote.git"), str(other)],
                check=True,
                capture_output=True,
            )
            git(other, "config", "user.email", "admin@example.com")
            git(other, "config", "user.name", "Admin")
            (other / "file.txt").write_text("two\n", encoding="utf-8")
            git(other, "commit", "-am", "second")
            git(other, "push")

            status = self.manager(root, clone).get_status(fetch_remote=True)

        self.assertEqual(status["status"], "behind")
        self.assertTrue(status["can_update"])
        self.assertEqual(status["behind"], 1)

    def test_status_blocks_tracked_local_edits(self):
        temp_dir, root, _remote, clone = self.make_repo_pair()
        with temp_dir:
            (clone / "file.txt").write_text("local\n", encoding="utf-8")
            status = self.manager(root, clone).get_status(fetch_remote=True)

        self.assertEqual(status["status"], "dirty")
        self.assertFalse(status["can_update"])

    def test_tag_checkout_is_pinned(self):
        temp_dir, root, _remote, clone = self.make_repo_pair()
        with temp_dir:
            git(clone, "tag", "v0.1.0")
            git(clone, "checkout", "v0.1.0")
            status = self.manager(root, clone).get_status(fetch_remote=True)

        self.assertEqual(status["source_type"], "tag")
        self.assertEqual(status["source_name"], "v0.1.0")
        self.assertEqual(status["status"], "pinned")
        self.assertFalse(status["can_update"])

    def test_update_now_refuses_when_not_updateable(self):
        temp_dir, root, _remote, clone = self.make_repo_pair()
        with temp_dir:
            manager = self.manager(root, clone)
            with self.assertRaises(AppUpdateError):
                manager.update_now()

    def test_update_now_uses_fast_forward_pull_and_installer(self):
        temp_dir, root, _remote, clone = self.make_repo_pair()
        with temp_dir:
            adapter = MagicMock()
            status_calls = [
                {
                    "can_update": True,
                    "message": "Update available.",
                },
                {
                    "can_update": False,
                    "message": "Up to date.",
                },
            ]
            manager = self.manager(root, clone, adapter=adapter)
            manager.get_status = MagicMock(side_effect=status_calls)
            adapter.run_git.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
            adapter.run_installer.return_value = SimpleNamespace(
                returncode=0,
                stdout="installed",
                stderr="",
            )

            result = manager.update_now()

        self.assertEqual(result["message"], "Up to date.")
        adapter.run_git.assert_called_once_with(
            clone,
            ["pull", "--ff-only"],
            check=False,
            timeout=None,
        )
        adapter.run_installer.assert_called_once_with(clone)
