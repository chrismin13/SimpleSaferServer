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

    def test_default_repo_path_uses_repo_root_even_when_data_dir_is_durable_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = SimpleNamespace(
                is_fake=False,
                repo_root=root / "app",
                data_dir=root / "var-lib",
                volatile_dir=root / "run",
            )
            manager = AppUpdateManager(runtime=runtime, command_adapter=MagicMock())

        self.assertEqual(manager.repo_path, runtime.repo_root)

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
        self.assertTrue(status["can_force_update"])
        self.assertEqual(status["tracked_change_count"], 1)
        self.assertEqual(status["untracked_file_count"], 0)
        self.assertEqual(status["dirty_files"], [{"path": "file.txt", "kind": "changed"}])
        self.assertIn("Changed app files are blocking the update", status["message"])

    def test_status_blocks_untracked_files(self):
        temp_dir, root, _remote, clone = self.make_repo_pair()
        with temp_dir:
            (clone / "extra.txt").write_text("extra\n", encoding="utf-8")
            status = self.manager(root, clone).get_status(fetch_remote=True)

        self.assertEqual(status["status"], "dirty")
        self.assertFalse(status["can_update"])
        self.assertTrue(status["can_force_update"])
        self.assertEqual(status["tracked_change_count"], 0)
        self.assertEqual(status["untracked_file_count"], 1)
        self.assertEqual(status["dirty_files"], [{"path": "extra.txt", "kind": "extra"}])
        self.assertIn("Extra app files are blocking the update", status["message"])

    def test_status_blocks_mixed_local_changes(self):
        temp_dir, root, _remote, clone = self.make_repo_pair()
        with temp_dir:
            (clone / "file.txt").write_text("local\n", encoding="utf-8")
            (clone / "extra.txt").write_text("extra\n", encoding="utf-8")
            status = self.manager(root, clone).get_status(fetch_remote=True)

        self.assertEqual(status["status"], "dirty")
        self.assertEqual(status["tracked_change_count"], 1)
        self.assertEqual(status["untracked_file_count"], 1)
        self.assertEqual(len(status["dirty_files"]), 2)
        self.assertIn({"path": "file.txt", "kind": "changed"}, status["dirty_files"])
        self.assertIn({"path": "extra.txt", "kind": "extra"}, status["dirty_files"])
        self.assertIn("Changed and extra app files", status["message"])

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
        self.assertFalse(status["can_force_update"])
        self.assertIn("pinned to a specific commit or tag", status["message"])

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

    def test_update_now_can_stream_pull_and_installer_to_journal(self):
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
            adapter.run_git_for_journal.return_value = SimpleNamespace(returncode=0)
            adapter.run_installer_for_journal.return_value = SimpleNamespace(returncode=0)

            result = manager.update_now(stream_to_journal=True)

        self.assertEqual(result["message"], "Up to date.")
        adapter.run_git_for_journal.assert_called_once_with(
            clone,
            ["pull", "--ff-only"],
            check=False,
            timeout=None,
        )
        adapter.run_installer_for_journal.assert_called_once_with(clone)
        adapter.run_git.assert_not_called()
        adapter.run_installer.assert_not_called()

    def test_force_update_runs_cleanup_fetch_pull_and_installer(self):
        temp_dir, root, _remote, clone = self.make_repo_pair()
        with temp_dir:
            adapter = MagicMock()
            manager = self.manager(root, clone, adapter=adapter)
            manager.get_status = MagicMock(
                side_effect=[
                    {
                        "can_force_update": True,
                        "message": "Changed app files are blocking the update.",
                    },
                    {
                        "can_update": False,
                        "message": "Up to date.",
                    },
                ]
            )
            adapter.run_git.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
            adapter.run_installer.return_value = SimpleNamespace(
                returncode=0,
                stdout="installed",
                stderr="",
            )

            result = manager.force_update_now()

        self.assertEqual(result["message"], "Up to date.")
        self.assertEqual(
            [call.args[1] for call in adapter.run_git.call_args_list],
            [
                ["reset", "--hard", "HEAD"],
                ["clean", "-fd"],
                ["fetch", "--prune", "--tags", "origin"],
                ["pull", "--ff-only"],
            ],
        )
        self.assertNotIn("-x", adapter.run_git.call_args_list[1].args[1])
        adapter.run_installer.assert_called_once_with(clone)

    def test_cleanup_update_request_is_volatile_and_consumed_once(self):
        temp_dir, root, _remote, clone = self.make_repo_pair()
        with temp_dir:
            manager = self.manager(root, clone)

            manager.request_cleanup_update()
            first_mode = manager.consume_update_request_mode()
            second_mode = manager.consume_update_request_mode()

        self.assertEqual(first_mode, "cleanup")
        self.assertEqual(second_mode, "normal")

    def test_branch_switch_request_is_volatile_and_consumed_once(self):
        temp_dir, root, _remote, clone = self.make_repo_pair()
        with temp_dir:
            manager = self.manager(root, clone)

            manager.request_branch_switch("main")
            first_request = manager.consume_update_request()
            second_request = manager.consume_update_request()

        self.assertEqual(first_request, {"mode": "switch_branch", "branch": "main"})
        self.assertEqual(second_request, {"mode": "normal"})

    def test_remote_branch_choices_include_origin_branches_without_head(self):
        temp_dir, root, _remote, clone = self.make_repo_pair()
        with temp_dir:
            git(clone, "checkout", "-b", "feature/demo")
            git(clone, "push", "-u", "origin", "feature/demo")

            branches = self.manager(root, clone).list_remote_branches(fetch_remote=True)

        self.assertEqual(branches, ["feature/demo", "master"])

    def test_switch_branch_runs_fetch_switch_pull_and_installer(self):
        temp_dir, root, _remote, clone = self.make_repo_pair()
        with temp_dir:
            adapter = MagicMock()
            manager = self.manager(root, clone, adapter=adapter)
            manager.get_status = MagicMock(
                side_effect=[
                    {
                        "dirty": False,
                        "message": "Pinned install.",
                    },
                    {
                        "source_type": "branch",
                        "source_name": "main",
                        "message": "Up to date with origin/main.",
                    },
                ]
            )
            manager.list_remote_branches = MagicMock(return_value=["main"])
            adapter.run_git.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
            adapter.run_installer.return_value = SimpleNamespace(
                returncode=0,
                stdout="installed",
                stderr="",
            )

            result = manager.switch_branch_now("main")

        self.assertEqual(result["source_name"], "main")
        self.assertEqual(
            [call.args[1] for call in adapter.run_git.call_args_list],
            [
                ["rev-parse", "--verify", "--quiet", "refs/heads/main"],
                ["branch", "--set-upstream-to", "origin/main", "main"],
                ["switch", "main"],
                ["pull", "--ff-only"],
            ],
        )
        manager.list_remote_branches.assert_called_once_with(fetch_remote=True)
        adapter.run_installer.assert_called_once_with(clone)

    def test_switch_branch_tracks_remote_when_local_branch_is_missing(self):
        temp_dir, root, _remote, clone = self.make_repo_pair()
        with temp_dir:
            adapter = MagicMock()
            manager = self.manager(root, clone, adapter=adapter)
            manager.get_status = MagicMock(
                side_effect=[
                    {
                        "dirty": False,
                        "message": "Pinned install.",
                    },
                    {
                        "source_type": "branch",
                        "source_name": "feature/demo",
                        "message": "Up to date with origin/feature/demo.",
                    },
                ]
            )
            manager.list_remote_branches = MagicMock(return_value=["feature/demo"])
            adapter.run_git.side_effect = [
                SimpleNamespace(returncode=1, stdout="", stderr=""),
                SimpleNamespace(returncode=0, stdout="", stderr=""),
                SimpleNamespace(returncode=0, stdout="", stderr=""),
            ]
            adapter.run_installer.return_value = SimpleNamespace(
                returncode=0,
                stdout="installed",
                stderr="",
            )

            result = manager.switch_branch_now("feature/demo")

        self.assertEqual(result["source_name"], "feature/demo")
        self.assertEqual(
            [call.args[1] for call in adapter.run_git.call_args_list],
            [
                ["rev-parse", "--verify", "--quiet", "refs/heads/feature/demo"],
                ["switch", "--track", "-c", "feature/demo", "origin/feature/demo"],
                ["pull", "--ff-only"],
            ],
        )
        adapter.run_installer.assert_called_once_with(clone)

    def test_switch_branch_refuses_dirty_checkout(self):
        temp_dir, root, _remote, clone = self.make_repo_pair()
        with temp_dir:
            adapter = MagicMock()
            manager = self.manager(root, clone, adapter=adapter)
            manager.get_status = MagicMock(
                return_value={
                    "dirty": True,
                    "message": "Changed app files are blocking the update.",
                }
            )

            with self.assertRaises(AppUpdateError) as error:
                manager.switch_branch_now("main")

        self.assertIn("Clean up app folder before switching branches", str(error.exception))
        adapter.run_git.assert_not_called()
        adapter.run_installer.assert_not_called()

    def test_switch_branch_refuses_missing_remote_branch(self):
        temp_dir, root, _remote, clone = self.make_repo_pair()
        with temp_dir:
            adapter = MagicMock()
            manager = self.manager(root, clone, adapter=adapter)
            manager.get_status = MagicMock(return_value={"dirty": False})
            manager.list_remote_branches = MagicMock(return_value=["main"])

            with self.assertRaises(AppUpdateError) as error:
                manager.switch_branch_now("feature/missing")

        self.assertIn("Branch is no longer available", str(error.exception))
        adapter.run_git.assert_not_called()
        adapter.run_installer.assert_not_called()

    def test_git_failure_diagnostic_includes_command_repo_return_code_and_output(self):
        temp_dir, root, _remote, clone = self.make_repo_pair()
        with temp_dir:
            adapter = MagicMock()
            manager = self.manager(root, clone, adapter=adapter)
            manager.get_status = MagicMock(return_value={"can_force_update": True})
            adapter.run_git.return_value = SimpleNamespace(
                returncode=2,
                stdout="out",
                stderr="err",
            )

            with self.assertRaises(AppUpdateError) as error:
                manager.force_update_now()

        detail = str(error.exception)
        self.assertIn("Command: git reset --hard HEAD", detail)
        self.assertIn(f"Repository: {clone}", detail)
        self.assertIn("Return code: 2", detail)
        self.assertIn("stdout:\nout", detail)
        self.assertIn("stderr:\nerr", detail)
