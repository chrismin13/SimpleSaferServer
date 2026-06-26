import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from simple_safer_server.adapters.command_runner import CalledProcessError, TimeoutExpired
from simple_safer_server.adapters.system_updates_commands import SystemUpdatesCommandAdapter
from simple_safer_server.services.file_persistence import atomic_write_json
from simple_safer_server.services.os_support import (
    DEFAULT_AUTOCLEAN_INTERVAL_DAYS,
    SUPPORT_SOURCES,
    get_support_info,
    parse_os_release_text,
)
from simple_safer_server.services.runtime import get_runtime

# psutil is optional in tests that exercise fallback lock detection paths.
psutil: Any | None = None
try:
    import psutil as _psutil
except ImportError:
    pass
else:
    psutil = _psutil

APT_LOCK_PATHS = [
    Path("/var/lib/dpkg/lock-frontend"),
    Path("/var/lib/dpkg/lock"),
    Path("/var/cache/apt/archives/lock"),
    Path("/var/lib/apt/lists/lock"),
]

APT_PROCESS_MARKERS = (
    "apt",
    "apt-get",
    "aptitude",
    "dpkg",
    "unattended-upgrade",
    "unattended-upgrades",
)

APP_UPDATE_UNAVAILABLE_MESSAGE = (
    "Application self-updates are unavailable until SSS has a release archive or package updater."
)


def _apt_process_token(value: Any) -> str:
    # Process names can be bare executable names, while argv entries may be full
    # paths; compare only the executable token so paths like /tmp/adapt do not
    # look like package-manager work.
    return Path(str(value or "")).name.lower()


def _apt_executable_candidates(name: str, cmdline_parts: list[str]) -> list[str]:
    candidates = [_apt_process_token(name)]
    argv_tokens = [_apt_process_token(part) for part in cmdline_parts if str(part or "").strip()]
    if not argv_tokens:
        return candidates

    candidates.append(argv_tokens[0])

    index = 0
    while index < len(argv_tokens):
        token = argv_tokens[index]
        # This is a command token, not a password.
        if token == "sudo":
            index += 1
            while index < len(argv_tokens) and argv_tokens[index].startswith("-"):
                index += 1
            continue
        # This is a command token, not a password.
        if token == "env":
            index += 1
            while index < len(argv_tokens):
                env_token = argv_tokens[index]
                if env_token.startswith("-") or "=" in env_token:
                    index += 1
                    continue
                break
            continue
        candidates.append(token)
        break

    return candidates


def _is_apt_process(name: str, cmdline_parts: list[str]) -> bool:
    return any(
        token in APT_PROCESS_MARKERS for token in _apt_executable_candidates(name, cmdline_parts)
    )


class SystemUpdatesManager:
    def __init__(self, config_manager, runtime=None, command_adapter=None):
        self.config_manager = config_manager
        self.runtime = runtime or get_runtime()
        self.command_adapter = command_adapter or SystemUpdatesCommandAdapter()
        self.state_path = self.runtime.volatile_dir / "system_updates_state.json"
        self.state_log_path = self.runtime.volatile_dir / "system_updates.log"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            self._write_state(self._default_state())

    def _default_state(self) -> dict[str, Any]:
        return {
            "operation": None,
            "status": "idle",
            "phase": "Idle",
            "progress": 0,
            "started_at": None,
            "finished_at": None,
            "returncode": None,
            "error": None,
            "log": "",
        }

    def get_application_update_status(self, *, fetch_remote: bool = False) -> dict[str, Any]:
        """Return the app-update status shown by the read-only System Updates page."""
        checked_at = datetime.now().isoformat(timespec="seconds")
        return {
            "source_type": "archive",
            "source_name": "Installer archive",
            "current_commit": "",
            "diagnostic": "",
            "status": "unavailable",
            "message": APP_UPDATE_UNAVAILABLE_MESSAGE,
            "can_update": False,
            "checked_at": checked_at,
            "last_remote_check_at": checked_at if fetch_remote else None,
        }

    def _read_state(self) -> dict[str, Any]:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            state = self._default_state()
        state = {**self._default_state(), **state}
        state["log"] = self._read_log()
        return state

    def _read_log(self) -> str:
        try:
            return self.state_log_path.read_text(encoding="utf-8")
        except Exception:
            return ""

    def _write_state(self, state: dict[str, Any]) -> None:
        state_without_log = dict(state)
        state_without_log.pop("log", None)
        # Readers poll this file from the UI, so replace it atomically instead
        # of exposing half-written JSON during an update.
        atomic_write_json(self.state_path, state_without_log, mode=0o644, durable=False)

    def _update_state(self, **updates) -> dict[str, Any]:
        state = self._read_state()
        state.update(updates)
        self._write_state(state)
        return state

    def get_distribution_info(self) -> dict[str, Any]:
        if self.runtime.is_fake:
            os_release = {
                "ID": "debian",
                "PRETTY_NAME": "Debian GNU/Linux 12 (bookworm)",
                "VERSION_ID": "12",
                "VERSION_CODENAME": "bookworm",
            }
        else:
            try:
                os_release = parse_os_release_text(Path("/etc/os-release").read_text())
            except Exception:
                os_release = {}

        distro_id = os_release.get("ID", "unknown").lower()
        version_id = os_release.get("VERSION_ID", "")
        support = get_support_info(distro_id, version_id)
        return {
            "id": distro_id,
            "pretty_name": os_release.get("PRETTY_NAME")
            or f"{distro_id} {version_id}".strip()
            or "Unknown Linux",
            "version_id": version_id,
            "version_codename": os_release.get("VERSION_CODENAME")
            or os_release.get("UBUNTU_CODENAME")
            or "",
            "support": support,
        }

    def _active_apt_processes(self) -> list[dict[str, Any]]:
        if psutil is None:
            return self._active_apt_processes_from_proc()

        processes: list[dict[str, Any]] = []
        current_pid = os.getpid()
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                info = proc.info
                if info.get("pid") == current_pid:
                    continue
                name = info.get("name") or ""
                cmdline_parts = info.get("cmdline") or []
                if _is_apt_process(name, cmdline_parts):
                    processes.append(
                        {
                            "pid": info.get("pid"),
                            "name": name,
                            "cmdline": " ".join(cmdline_parts),
                        }
                    )
            except psutil.NoSuchProcess, psutil.AccessDenied:
                continue
        return processes

    def _active_apt_processes_from_proc(self) -> list[dict[str, Any]]:
        """Fallback for minimal test/dev environments where psutil is absent."""
        processes: list[dict[str, Any]] = []
        current_pid = os.getpid()
        proc_root = Path("/proc")
        if not proc_root.exists():
            return processes

        for pid_dir in proc_root.iterdir():
            if not pid_dir.name.isdigit():
                continue
            pid = int(pid_dir.name)
            if pid == current_pid:
                continue
            try:
                name = (pid_dir / "comm").read_text().strip()
                raw_cmdline_bytes = (pid_dir / "cmdline").read_bytes()
                cmdline_parts = [
                    part.decode(errors="ignore")
                    for part in raw_cmdline_bytes.split(b"\x00")
                    if part
                ]
            # /proc entries can disappear while scanning.
            except Exception:
                continue
            if _is_apt_process(name, cmdline_parts):
                processes.append({"pid": pid, "name": name, "cmdline": " ".join(cmdline_parts)})
        return processes

    def _held_lock_paths(self) -> list[str]:
        if self.runtime.is_fake:
            return []

        held: list[str] = []
        fuser = shutil.which("fuser")
        if not fuser:
            return held
        for path in APT_LOCK_PATHS:
            if not path.exists():
                continue
            if self.command_adapter.is_lock_held(fuser, path):
                held.append(str(path))
        return held

    def is_own_operation_running(self) -> bool:
        return False

    def get_lock_status(self) -> dict[str, Any]:
        own_running = self.is_own_operation_running()
        processes = [] if self.runtime.is_fake else self._active_apt_processes()
        held_locks = self._held_lock_paths()
        return {
            "locked": own_running or bool(processes) or bool(held_locks),
            "own_operation_running": own_running,
            "held_locks": held_locks,
            "processes": processes[:8],
        }

    def _reconcile_running_state(
        self, state: dict[str, Any], lock_status: dict[str, Any]
    ) -> dict[str, Any]:
        if state.get("status") != "running" or lock_status["own_operation_running"]:
            return state

        if lock_status["processes"] or lock_status["held_locks"]:
            updates: dict[str, Any] = {
                "status": "external",
                "phase": "Package manager busy",
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "error": (
                    "SimpleSaferServer restarted while this apt operation was running. "
                    "Another apt or dpkg process is still active."
                ),
            }
        else:
            updates: dict[str, Any] = {
                "status": "failure",
                "phase": "Interrupted",
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "error": "SimpleSaferServer restarted before this apt operation finished.",
            }

        # A persisted running state only proves a previous service process
        # started work; after restart, only the in-memory worker can be stopped.
        updates["returncode"] = None
        return self._update_state(**updates)

    def get_status(self) -> dict[str, Any]:
        state = self._read_state()
        lock_status = self.get_lock_status()
        state = self._reconcile_running_state(state, lock_status)
        state["lock"] = lock_status
        return state

    def _parse_apt_periodic_config(self, text: str) -> dict[str, Any]:
        values: dict[str, Any] = {}
        key_map = {
            "Update-Package-Lists": "update_package_lists",
            "Unattended-Upgrade": "unattended_upgrade",
            "AutocleanInterval": "autoclean_interval",
        }
        for apt_key, settings_key in key_map.items():
            match = re.search(rf'APT::Periodic::{re.escape(apt_key)}\s+"?(\d+)"?\s*;', text)
            if not match:
                continue
            parsed_value = int(match.group(1))
            values[settings_key] = (
                parsed_value if settings_key == "autoclean_interval" else parsed_value > 0
            )
        return values

    def _read_apt_periodic_config(self) -> dict[str, Any]:
        path = Path("/etc/apt/apt.conf.d/20auto-upgrades")
        if self.runtime.is_fake or not path.exists():
            return {}
        try:
            text = path.read_text()
        except Exception:
            return {}
        return self._parse_apt_periodic_config(text)

    def get_settings(self) -> dict[str, Any]:
        system_values = self._read_apt_periodic_config()
        update_lists = system_values.get("update_package_lists", False)
        unattended = system_values.get("unattended_upgrade", False)
        autoclean_interval = system_values.get(
            "autoclean_interval", DEFAULT_AUTOCLEAN_INTERVAL_DAYS
        )
        return {
            "apt_updates_managed": False,
            "read_only": True,
            "update_package_lists": self._coerce_bool(update_lists, False),
            "unattended_upgrade": self._coerce_bool(unattended, False),
            "autoclean": autoclean_interval > 0,
            "autoclean_interval": autoclean_interval,
        }

    def _coerce_bool(self, value: str | None, default: bool) -> bool:
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def get_livepatch_status(self) -> dict[str, Any]:
        def status_command_failed(exc: Exception) -> dict[str, Any]:
            return {
                "supported_distro": True,
                "installed": False,
                "enabled": False,
                "status_text": f"Livepatch status unavailable: {exc}",
                "details": {},
                "source_url": SUPPORT_SOURCES["livepatch"],
            }

        distro = self.get_distribution_info()
        if distro["id"] != "ubuntu":
            return {
                "supported_distro": False,
                "installed": False,
                "enabled": False,
                "status_text": "Ubuntu Livepatch is only available on Ubuntu.",
                "source_url": SUPPORT_SOURCES["livepatch"],
            }

        binary = shutil.which("canonical-livepatch")
        if self.runtime.is_fake:
            return {
                "supported_distro": True,
                "installed": True,
                "enabled": True,
                "status_text": "Fake mode: Livepatch is enabled and current.",
                "details": {},
                "source_url": SUPPORT_SOURCES["livepatch"],
            }
        if not binary:
            return {
                "supported_distro": True,
                "installed": False,
                "enabled": False,
                "status_text": "canonical-livepatch is not installed.",
                "source_url": SUPPORT_SOURCES["livepatch"],
            }

        try:
            result = self.command_adapter.livepatch_status_json(binary)
        except (CalledProcessError, OSError, TimeoutExpired) as exc:
            return status_command_failed(exc)
        if result.returncode == 0:
            try:
                details = json.loads(result.stdout or "{}")
            except json.JSONDecodeError:
                details = {"raw": result.stdout.strip()}
            status_text = self._summarize_livepatch_details(details)
            return {
                "supported_distro": True,
                "installed": True,
                "enabled": True,
                "status_text": status_text,
                "details": details,
                "source_url": SUPPORT_SOURCES["livepatch"],
            }

        try:
            fallback = self.command_adapter.livepatch_status_text(binary)
        except (CalledProcessError, OSError, TimeoutExpired) as exc:
            return status_command_failed(exc)
        output = (
            fallback.stdout or fallback.stderr or result.stderr or "Livepatch status unavailable."
        ).strip()
        return {
            "supported_distro": True,
            "installed": True,
            "enabled": False,
            "status_text": output,
            "details": {},
            "source_url": SUPPORT_SOURCES["livepatch"],
        }

    def _summarize_livepatch_details(self, details: dict[str, Any]) -> str:
        status = details.get("status") or details.get("Status") or []
        if isinstance(status, list) and status:
            kernel = status[0].get("kernel") or status[0].get("Kernel") or "kernel"
            state = status[0].get("livepatch") or status[0].get("Livepatch") or "status available"
            return f"{kernel}: {state}"
        return "Livepatch status is available."
