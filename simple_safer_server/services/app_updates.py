import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from simple_safer_server.adapters.app_update_commands import AppUpdateCommandAdapter
from simple_safer_server.adapters.command_runner import CalledProcessError
from simple_safer_server.services.file_persistence import atomic_write_json
from simple_safer_server.services.runtime import get_runtime


class AppUpdateError(RuntimeError):
    """Raised when the application cannot safely update itself."""


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
            dirty_output = self._git_stdout(
                ["status", "--porcelain", "--untracked-files=no"], check=False
            )
        except (CalledProcessError, OSError) as exc:
            return self._empty_status("unavailable", f"Git status is unavailable: {exc}")

        status = {
            "source_type": source_type,
            "source_name": source_name,
            "current_commit": short_commit,
            "current_commit_full": full_commit,
            "upstream": "",
            "ahead": None,
            "behind": None,
            "dirty": bool(dirty_output),
            "status": "unchecked",
            "message": "Remote status has not been checked yet.",
            "can_update": False,
            "checked_at": self._now(),
            "last_remote_check_at": None,
        }

        if status["dirty"]:
            status["status"] = "dirty"
            status["message"] = "Local tracked file edits block automatic updates."
            return status

        if source_type != "branch":
            status["status"] = "pinned"
            status["message"] = "This checkout is pinned and will not auto-update."
            return status

        upstream = self._git_stdout(
            ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], check=False
        )
        if not upstream:
            status["status"] = "unavailable"
            status["message"] = "This branch does not have an upstream configured."
            return status
        status["upstream"] = upstream
        return status

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
                status["message"] = f"Remote update status is unavailable: {exc}"
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
            raise AppUpdateError((pull.stderr or pull.stdout or "git pull failed.").strip())

        installer = self.command_adapter.run_installer(self.repo_path)
        if installer.returncode != 0:
            raise AppUpdateError(
                (installer.stderr or installer.stdout or "Application installer failed.").strip()
            )

        return self.get_status(fetch_remote=False)
