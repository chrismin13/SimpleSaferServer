import json
import shlex
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from simple_safer_server.adapters.app_update_commands import AppUpdateCommandAdapter
from simple_safer_server.adapters.command_runner import CalledProcessError
from simple_safer_server.services.file_persistence import atomic_write_json
from simple_safer_server.services.runtime import get_runtime


class AppUpdateError(RuntimeError):
    """Raised when the application cannot safely update itself."""


def _format_process_failure(
    command: List[str], repo_path: Path, returncode: int, stdout: str, stderr: str
) -> str:
    command_text = " ".join(shlex.quote(part) for part in command)
    return (
        f"Command: {command_text}\n"
        f"Repository: {repo_path}\n"
        f"Return code: {returncode}\n"
        f"stdout:\n{stdout or ''}\n"
        f"stderr:\n{stderr or ''}"
    )


class AppUpdateManager:
    def __init__(self, runtime=None, command_adapter=None, repo_path: Optional[Path] = None):
        self.runtime = runtime or get_runtime()
        self.repo_path = Path(repo_path) if repo_path is not None else self._default_repo_path()
        self.command_adapter = command_adapter or AppUpdateCommandAdapter()
        self.cache_path = self.runtime.volatile_dir / "app_update_status.json"
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

    def _default_repo_path(self) -> Path:
        if self.runtime.is_fake:
            return self.runtime.repo_root
        return self.runtime.data_dir

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _git(self, args, *, check=False, timeout=None):
        return self.command_adapter.run_git(
            self.repo_path,
            list(args),
            check=check,
            timeout=timeout,
        )

    def _git_stdout(self, args, *, check=False) -> str:
        result = self._git(args, check=check)
        return (result.stdout or "").strip()

    def _git_failure_detail(self, exc: CalledProcessError) -> str:
        command = list(exc.cmd[1:] if exc.cmd and exc.cmd[0] == "git" else exc.cmd)
        return _format_process_failure(
            ["git", *command],
            self.repo_path,
            exc.returncode,
            exc.stdout or "",
            exc.stderr or "",
        )

    def _process_failure_detail(self, command: List[str], result) -> str:
        return _format_process_failure(
            command,
            self.repo_path,
            result.returncode,
            result.stdout or "",
            result.stderr or "",
        )

    def _empty_status(self, status: str, message: str) -> Dict[str, Any]:
        return {
            "source_type": "unknown",
            "source_name": "",
            "current_commit": "",
            "current_commit_full": "",
            "upstream": "",
            "ahead": None,
            "behind": None,
            "dirty": False,
            "tracked_change_count": 0,
            "untracked_file_count": 0,
            "can_force_update": False,
            "diagnostic": "",
            "status": status,
            "message": message,
            "can_update": False,
            "checked_at": None,
            "last_remote_check_at": None,
        }

    def _read_cache(self) -> Dict[str, Any]:
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_cache(self, status: Dict[str, Any]) -> None:
        atomic_write_json(self.cache_path, status, mode=0o644, durable=False)

    def _source_info(self) -> Tuple[str, str]:
        branch = self._git_stdout(["symbolic-ref", "--quiet", "--short", "HEAD"], check=False)
        if branch:
            return "branch", branch

        tag = self._git_stdout(["describe", "--tags", "--exact-match"], check=False)
        if tag:
            return "tag", tag

        commit = self._git_stdout(["rev-parse", "--short", "HEAD"], check=False)
        return "detached", commit

    def _base_status(self) -> Dict[str, Any]:
        if not (self.repo_path / ".git").exists():
            return self._empty_status(
                "unavailable",
                "The installed application directory is not a Git checkout.",
            )

        try:
            full_commit = self._git_stdout(["rev-parse", "HEAD"], check=True)
            short_commit = self._git_stdout(["rev-parse", "--short", "HEAD"], check=True)
            source_type, source_name = self._source_info()
            status_output = self._git_stdout(["status", "--porcelain"], check=False)
        except CalledProcessError as exc:
            status = self._empty_status("unavailable", "Git status is unavailable.")
            status["diagnostic"] = self._git_failure_detail(exc)
            return status
        except OSError as exc:
            status = self._empty_status("unavailable", "Git status is unavailable.")
            status["diagnostic"] = str(exc)
            return status

        tracked_change_count, untracked_file_count = self._status_counts(status_output)

        status = {
            "source_type": source_type,
            "source_name": source_name,
            "current_commit": short_commit,
            "current_commit_full": full_commit,
            "upstream": "",
            "ahead": None,
            "behind": None,
            "dirty": bool(status_output),
            "tracked_change_count": tracked_change_count,
            "untracked_file_count": untracked_file_count,
            "can_force_update": False,
            "diagnostic": "",
            "status": "unchecked",
            "message": "Remote status has not been checked yet.",
            "can_update": False,
            "checked_at": self._now(),
            "last_remote_check_at": None,
        }

        upstream = ""
        if source_type == "branch":
            upstream = self._git_stdout(
                ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], check=False
            )
            status["upstream"] = upstream

        if status["dirty"]:
            status["status"] = "dirty"
            # Cleanup is only actionable when a branch has an upstream to fast-forward after reset.
            status["can_force_update"] = source_type == "branch" and bool(upstream)
            if tracked_change_count and untracked_file_count:
                status["message"] = (
                    "Changed or extra files in the app folder are blocking the update. "
                    "Use Clean Up and Update to reset the app folder and continue."
                )
            elif tracked_change_count:
                status["message"] = (
                    "Changed app files are blocking the update. This can happen after manual "
                    "troubleshooting or older installer behavior. Use Clean Up and Update to "
                    "reset the app folder and continue."
                )
            else:
                status["message"] = (
                    "Extra files in the app folder are blocking the update. This can happen "
                    "after older installs. Use Clean Up and Update to remove extra app-folder "
                    "files and continue."
                )
            return status

        if source_type != "branch":
            status["status"] = "pinned"
            status["message"] = (
                "This install is pinned to a specific commit or tag, so automatic branch updates "
                "are not available."
            )
            return status

        if not upstream:
            status["status"] = "unavailable"
            status["message"] = "This branch does not have an upstream configured."
            return status
        return status

    def _status_counts(self, status_output: str) -> Tuple[int, int]:
        tracked_change_count = 0
        untracked_file_count = 0
        for line in status_output.splitlines():
            if line.startswith("??"):
                untracked_file_count += 1
            elif line:
                tracked_change_count += 1
        return tracked_change_count, untracked_file_count

    def _apply_counts(self, status: Dict[str, Any]) -> Dict[str, Any]:
        counts = self._git_stdout(
            ["rev-list", "--left-right", "--count", "HEAD...@{u}"], check=True
        )
        parts = counts.split()
        ahead = int(parts[0])
        behind = int(parts[1])
        status["ahead"] = ahead
        status["behind"] = behind
        status["last_remote_check_at"] = self._now()
        if ahead and behind:
            status["status"] = "diverged"
            status["message"] = f"This branch has diverged from {status['upstream']}."
        elif ahead:
            status["status"] = "ahead"
            status["message"] = (
                f"This branch is {ahead} commit{'s' if ahead != 1 else ''} ahead of {status['upstream']}."
            )
        elif behind:
            status["status"] = "behind"
            status["message"] = (
                f"Update available: {behind} commit{'s' if behind != 1 else ''} behind {status['upstream']}."
            )
            status["can_update"] = True
        else:
            status["status"] = "up_to_date"
            status["message"] = f"Up to date with {status['upstream']}."
        return status

    def get_status(self, *, fetch_remote: bool = False) -> Dict[str, Any]:
        status = self._base_status()
        if status["status"] in {"unavailable", "dirty", "pinned"}:
            self._write_cache(status)
            return status

        if fetch_remote:
            try:
                self._git(["fetch", "--prune", "--tags", "origin"], check=True)
                status = self._apply_counts(status)
            except (CalledProcessError, OSError, ValueError) as exc:
                status["status"] = "unavailable"
                status["message"] = "Remote update status is unavailable."
                if isinstance(exc, CalledProcessError):
                    status["diagnostic"] = self._git_failure_detail(exc)
                else:
                    status["diagnostic"] = str(exc)
                status["can_update"] = False
                status["last_remote_check_at"] = self._now()
            self._write_cache(status)
            return status

        cache = self._read_cache()
        if cache.get("current_commit_full") == status.get("current_commit_full"):
            for key in ("ahead", "behind", "last_remote_check_at"):
                status[key] = cache.get(key)
            if cache.get("status") in {"up_to_date", "behind", "ahead", "diverged"}:
                status["status"] = cache.get("status")
                status["message"] = cache.get("message", status["message"])
                status["can_update"] = bool(cache.get("can_update"))
        return status

    def update_now(self) -> Dict[str, Any]:
        status = self.get_status(fetch_remote=True)
        if not status.get("can_update"):
            raise AppUpdateError(status.get("message") or "Application update is not available.")

        pull = self._git(["pull", "--ff-only"], check=False)
        if pull.returncode != 0:
            raise AppUpdateError(self._process_failure_detail(["git", "pull", "--ff-only"], pull))

        installer = self.command_adapter.run_installer(self.repo_path)
        if installer.returncode != 0:
            raise AppUpdateError(self._process_failure_detail(["bash", "install.sh"], installer))

        return self.get_status(fetch_remote=False)

    def force_update_now(self) -> Dict[str, Any]:
        status = self.get_status(fetch_remote=False)
        if not status.get("can_force_update"):
            raise AppUpdateError(status.get("message") or "Application cleanup is not available.")

        commands = [
            (["reset", "--hard", "HEAD"], ["git", "reset", "--hard", "HEAD"]),
            (["clean", "-fd"], ["git", "clean", "-fd"]),
            (
                ["fetch", "--prune", "--tags", "origin"],
                ["git", "fetch", "--prune", "--tags", "origin"],
            ),
            (["pull", "--ff-only"], ["git", "pull", "--ff-only"]),
        ]
        for git_args, command in commands:
            result = self._git(git_args, check=False)
            if result.returncode != 0:
                raise AppUpdateError(self._process_failure_detail(command, result))

        installer = self.command_adapter.run_installer(self.repo_path)
        if installer.returncode != 0:
            raise AppUpdateError(self._process_failure_detail(["bash", "install.sh"], installer))

        return self.get_status(fetch_remote=False)
