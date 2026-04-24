import json
import os
import shutil
import signal
import subprocess
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import psutil
except ImportError:
    psutil = None

from runtime import get_runtime


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


SUPPORT_INFO = {
    "debian": {
        # Debian LTS dates are used for support status where available.
        # Debian ELTS dates are intentionally excluded because ELTS is externally
        # provided paid support and is not generally available by default.
        "13": {
            "standard_eol": "2028-08-09",
            "standard_eol_display": "August 9, 2028",
            "max_eol": "2030-06-30",
            "max_eol_display": "June 30, 2030",
            "notes": "Support status includes Debian LTS but excludes paid ELTS.",
        },
        "12": {
            "standard_eol": "2026-06-10",
            "standard_eol_display": "June 10, 2026",
            "max_eol": "2028-06-30",
            "max_eol_display": "June 30, 2028",
            "notes": "Support status includes Debian LTS but excludes paid ELTS.",
        },
        "11": {
            "standard_eol": "2024-08-14",
            "standard_eol_display": "August 14, 2024",
            "max_eol": "2026-08-31",
            "max_eol_display": "August 31, 2026",
            "notes": "Support status includes Debian LTS but excludes paid ELTS.",
        },
        "10": {
            "standard_eol": "2022-09-10",
            "standard_eol_display": "September 10, 2022",
            "max_eol": "2024-06-30",
            "max_eol_display": "June 30, 2024",
            "notes": "Support status includes Debian LTS but excludes paid ELTS.",
        },
    },
    "ubuntu": {
        # Ubuntu Pro ESM is available through free personal subscriptions; the
        # paid Legacy support add-on dates are intentionally excluded here.
        "26.04": {
            "standard_eol": "2031-07-31",
            "standard_eol_display": "July 2031",
            "max_eol": "2036-04-30",
            "max_eol_display": "April 2036",
            "notes": "Support status includes Ubuntu Pro ESM but excludes the paid Legacy support add-on.",
        },
        "25.10": {
            "standard_eol": "2026-07-31",
            "standard_eol_display": "July 2026",
            "max_eol": "2026-07-31",
            "max_eol_display": "July 2026",
            "notes": "Interim Ubuntu releases receive short standard support only.",
        },
        "24.04": {
            "standard_eol": "2029-06-30",
            "standard_eol_display": "June 2029",
            "max_eol": "2034-04-30",
            "max_eol_display": "April 2034",
            "notes": "Support status includes Ubuntu Pro ESM but excludes the paid Legacy support add-on.",
        },
        "22.04": {
            "standard_eol": "2027-06-30",
            "standard_eol_display": "June 2027",
            "max_eol": "2032-04-30",
            "max_eol_display": "April 2032",
            "notes": "Support status includes Ubuntu Pro ESM but excludes the paid Legacy support add-on.",
        },
        "20.04": {
            "standard_eol": "2025-05-31",
            "standard_eol_display": "May 2025",
            "max_eol": "2030-04-30",
            "max_eol_display": "April 2030",
            "notes": "Support status includes Ubuntu Pro ESM but excludes the paid Legacy support add-on.",
        },
        "18.04": {
            "standard_eol": "2023-05-31",
            "standard_eol_display": "May 2023",
            "max_eol": "2028-04-30",
            "max_eol_display": "April 2028",
            "notes": "Support status includes Ubuntu Pro ESM but excludes the paid Legacy support add-on.",
        },
    },
}

SUPPORT_SOURCES = {
    "debian": "https://wiki.debian.org/DebianReleases",
    "ubuntu": "https://documentation.ubuntu.com/project/release-team/list-of-releases/",
    "livepatch": "https://ubuntu.com/security/livepatch/docs/livepatch/how-to/status",
}

EOL_WARNING_DAYS = 183


def parse_os_release_text(text: str) -> Dict[str, str]:
    """Parse os-release without shelling out; this file is the distro source of truth."""
    values: Dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"')
    return values


def _major_debian_version(version_id: str) -> str:
    return (version_id or "").split(".", 1)[0]


def _major_ubuntu_version(version_id: str) -> str:
    parts = (version_id or "").split(".")
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return version_id


def get_support_info(distro_id: str, version_id: str, today: Optional[date] = None) -> Dict[str, Any]:
    distro = (distro_id or "").lower()
    lookup_version = version_id
    if distro == "debian":
        lookup_version = _major_debian_version(version_id)
    elif distro == "ubuntu":
        lookup_version = _major_ubuntu_version(version_id)

    info = SUPPORT_INFO.get(distro, {}).get(lookup_version)
    if not info:
        return {
            "known": False,
            "standard_eol": None,
            "standard_eol_display": "Unknown",
            "max_eol": None,
            "max_eol_display": "Unknown",
            "notes": "Support dates are not built into this version of SimpleSaferServer.",
            "source_url": SUPPORT_SOURCES.get(distro),
            "approaching_eol": False,
            "days_until_eol": None,
        }

    today = today or date.today()
    max_eol = info.get("max_eol")
    is_supported = None
    days_until_eol = None
    approaching_eol = False
    if max_eol:
        max_eol_date = datetime.strptime(max_eol, "%Y-%m-%d").date()
        days_until_eol = (max_eol_date - today).days
        is_supported = days_until_eol >= 0
        # Six calendar months is not a fixed number of days; 183 keeps the UI
        # warning threshold simple and errs slightly early.
        approaching_eol = is_supported and days_until_eol <= EOL_WARNING_DAYS

    return {
        "known": True,
        "standard_eol": info.get("standard_eol"),
        "standard_eol_display": info.get("standard_eol_display"),
        "max_eol": max_eol,
        "max_eol_display": info.get("max_eol_display"),
        "notes": info.get("notes", ""),
        "source_url": SUPPORT_SOURCES.get(distro),
        "is_supported": is_supported,
        "approaching_eol": approaching_eol,
        "days_until_eol": days_until_eol,
    }


class SystemUpdatesManager:
    def __init__(self, config_manager, runtime=None):
        self.config_manager = config_manager
        self.runtime = runtime or get_runtime()
        self.state_path = self.runtime.data_dir / "system_updates_state.json"
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._process: Optional[subprocess.Popen] = None
        self._cancel_event: Optional[threading.Event] = None
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            self._write_state(self._default_state())

    def _default_state(self) -> Dict[str, Any]:
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

    def _read_state(self) -> Dict[str, Any]:
        try:
            state = json.loads(self.state_path.read_text())
        except Exception:
            state = self._default_state()
        return {**self._default_state(), **state}

    def _write_state(self, state: Dict[str, Any]) -> None:
        self.state_path.write_text(json.dumps(state, indent=2))
        self.state_path.chmod(0o644)

    def _update_state(self, **updates) -> Dict[str, Any]:
        with self._lock:
            state = self._read_state()
            state.update(updates)
            self._write_state(state)
            return state

    def _append_log(self, line: str) -> None:
        if not line:
            return
        with self._lock:
            state = self._read_state()
            current = state.get("log", "")
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            state["log"] = f"{current}{timestamp} {line.rstrip()}\n"
            self._write_state(state)

    def get_distribution_info(self) -> Dict[str, Any]:
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
            "pretty_name": os_release.get("PRETTY_NAME") or f"{distro_id} {version_id}".strip() or "Unknown Linux",
            "version_id": version_id,
            "version_codename": os_release.get("VERSION_CODENAME") or os_release.get("UBUNTU_CODENAME") or "",
            "support": support,
        }

    def _active_apt_processes(self) -> List[Dict[str, Any]]:
        if psutil is None:
            return self._active_apt_processes_from_proc()

        processes: List[Dict[str, Any]] = []
        current_pid = os.getpid()
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                info = proc.info
                if info.get("pid") == current_pid:
                    continue
                name = (info.get("name") or "").lower()
                cmdline_parts = info.get("cmdline") or []
                cmdline = " ".join(cmdline_parts).lower()
                if any(marker in name or marker in cmdline for marker in APT_PROCESS_MARKERS):
                    processes.append({
                        "pid": info.get("pid"),
                        "name": info.get("name") or "",
                        "cmdline": " ".join(cmdline_parts),
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return processes

    def _active_apt_processes_from_proc(self) -> List[Dict[str, Any]]:
        """Fallback for minimal test/dev environments where psutil is absent."""
        processes: List[Dict[str, Any]] = []
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
                raw_cmdline = (pid_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="ignore")
            except Exception:
                continue
            lowered = f"{name} {raw_cmdline}".lower()
            if any(marker in lowered for marker in APT_PROCESS_MARKERS):
                processes.append({"pid": pid, "name": name, "cmdline": raw_cmdline.strip()})
        return processes

    def _held_lock_paths(self) -> List[str]:
        if self.runtime.is_fake:
            state = self._read_state()
            return [str(APT_LOCK_PATHS[0])] if state.get("status") == "running" else []

        held: List[str] = []
        fuser = shutil.which("fuser")
        if not fuser:
            return held
        for path in APT_LOCK_PATHS:
            if not path.exists():
                continue
            result = subprocess.run([fuser, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if result.returncode == 0:
                held.append(str(path))
        return held

    def is_own_operation_running(self) -> bool:
        with self._lock:
            return bool(self._thread and self._thread.is_alive())

    def get_lock_status(self) -> Dict[str, Any]:
        own_running = self.is_own_operation_running()
        processes = [] if self.runtime.is_fake else self._active_apt_processes()
        held_locks = self._held_lock_paths()
        return {
            "locked": own_running or bool(processes) or bool(held_locks),
            "own_operation_running": own_running,
            "held_locks": held_locks,
            "processes": processes[:8],
        }

    def _command_for_operation(self, operation: str) -> List[str]:
        if operation == "update":
            return ["sudo", "apt-get", "update"]
        if operation == "upgrade":
            return ["sudo", "env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "-y", "upgrade"]
        raise ValueError("Unsupported apt operation.")

    def _progress_from_line(self, operation: str, line: str, current_progress: int) -> Tuple[int, str]:
        text = line.strip()
        lowered = text.lower()
        if operation == "update":
            if lowered.startswith(("get:", "hit:", "ign:")):
                return min(max(current_progress + 3, 15), 78), "Downloading package indexes"
            if "reading package lists" in lowered:
                return 92, "Reading package lists"
            return max(current_progress, 10), "Updating package indexes"

        if "reading package lists" in lowered:
            return max(current_progress, 12), "Reading package lists"
        if "building dependency tree" in lowered:
            return max(current_progress, 24), "Building dependency tree"
        if "calculating upgrade" in lowered:
            return max(current_progress, 34), "Calculating upgrade"
        if lowered.startswith(("get:", "need to get")):
            return min(max(current_progress + 4, 42), 62), "Downloading packages"
        if "unpacking" in lowered:
            return min(max(current_progress + 3, 58), 76), "Unpacking packages"
        if "setting up" in lowered:
            return min(max(current_progress + 3, 72), 88), "Configuring packages"
        if "processing triggers" in lowered:
            return max(current_progress, 92), "Processing triggers"
        return max(current_progress, 8), "Upgrading packages"

    def start_operation(self, operation: str) -> Dict[str, Any]:
        if operation not in {"update", "upgrade"}:
            raise ValueError("Operation must be update or upgrade.")
        with self._lock:
            if self.is_own_operation_running():
                raise RuntimeError("A system update operation is already running.")
            lock_status = self.get_lock_status()
            if lock_status["locked"]:
                raise RuntimeError("Apt is already busy. Wait for the current package operation to finish.")

            cancel_event = threading.Event()
            self._cancel_event = cancel_event
            self._update_state(
                operation=operation,
                status="running",
                phase="Starting",
                progress=3,
                started_at=datetime.now().isoformat(timespec="seconds"),
                finished_at=None,
                returncode=None,
                error=None,
                log="",
            )
            target = self._run_fake_operation if self.runtime.is_fake else self._run_real_operation
            thread = threading.Thread(
                target=target,
                args=(operation, cancel_event),
                name=f"system-updates-{operation}",
                daemon=True,
            )
            self._thread = thread
            thread.start()
            return self.get_status()

    def _run_fake_operation(self, operation: str, cancel_event: threading.Event) -> None:
        phases = (
            ["Checking package indexes", "Downloading package indexes", "Reading package lists"]
            if operation == "update"
            else ["Reading package lists", "Downloading packages", "Unpacking packages", "Configuring packages"]
        )
        try:
            for index, phase in enumerate(phases, start=1):
                if cancel_event.is_set():
                    raise RuntimeError("Operation was stopped.")
                progress = min(95, int(index / len(phases) * 90))
                self._append_log(f"Fake mode: {phase}.")
                self._update_state(progress=progress, phase=phase)
                time.sleep(0.4)
            self._update_state(
                status="success",
                phase="Complete",
                progress=100,
                finished_at=datetime.now().isoformat(timespec="seconds"),
                returncode=0,
            )
            self._append_log(f"Fake mode: apt {operation} completed.")
        except Exception as exc:
            status = "stopped" if cancel_event.is_set() else "failure"
            self._update_state(
                status=status,
                phase="Stopped" if status == "stopped" else "Failed",
                finished_at=datetime.now().isoformat(timespec="seconds"),
                error=str(exc),
            )
            self._append_log(str(exc))

    def _run_real_operation(self, operation: str, cancel_event: threading.Event) -> None:
        command = self._command_for_operation(operation)
        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"
        try:
            self._append_log(f"Running: {' '.join(command)}")
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                preexec_fn=os.setsid,
            )
            with self._lock:
                self._process = proc

            progress = 5
            if proc.stdout:
                for raw_line in iter(proc.stdout.readline, ""):
                    if not raw_line and proc.poll() is not None:
                        break
                    line = raw_line.rstrip()
                    if line:
                        self._append_log(line)
                        progress, phase = self._progress_from_line(operation, line, progress)
                        self._update_state(progress=progress, phase=phase)
                    if cancel_event.is_set():
                        break

            if cancel_event.is_set() and proc.poll() is None:
                self._terminate_process(proc)

            returncode = proc.wait()
            if cancel_event.is_set():
                self._update_state(
                    status="stopped",
                    phase="Stopped",
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                    returncode=returncode,
                    error="Operation was stopped.",
                )
            elif returncode == 0:
                self._update_state(
                    status="success",
                    phase="Complete",
                    progress=100,
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                    returncode=returncode,
                )
            else:
                self._update_state(
                    status="failure",
                    phase="Failed",
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                    returncode=returncode,
                    error=f"apt-get exited with code {returncode}.",
                )
        except Exception as exc:
            status = "stopped" if cancel_event.is_set() else "failure"
            self._update_state(
                status=status,
                phase="Stopped" if status == "stopped" else "Failed",
                finished_at=datetime.now().isoformat(timespec="seconds"),
                error=str(exc),
            )
            self._append_log(str(exc))
        finally:
            with self._lock:
                self._process = None
                self._cancel_event = None

    def _terminate_process(self, proc: subprocess.Popen) -> None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()

    def stop_operation(self) -> Dict[str, Any]:
        with self._lock:
            if not self.is_own_operation_running() or not self._cancel_event:
                raise RuntimeError("No SimpleSaferServer apt operation is running.")
            self._cancel_event.set()
            proc = self._process
        if proc and proc.poll() is None:
            self._terminate_process(proc)
        self._update_state(phase="Stopping")
        return self.get_status()

    def get_status(self) -> Dict[str, Any]:
        state = self._read_state()
        state["lock"] = self.get_lock_status()
        return state

    def remove_stale_locks(self) -> Dict[str, Any]:
        lock_status = self.get_lock_status()
        if lock_status["processes"] or lock_status["own_operation_running"] or lock_status["held_locks"]:
            raise RuntimeError("Apt or dpkg is running. Stop or wait for it before removing stale locks.")

        existing = [str(path) for path in APT_LOCK_PATHS if path.exists()]
        if self.runtime.is_fake:
            return {"removed": existing or [str(APT_LOCK_PATHS[0])], "message": "Fake mode: stale apt locks removed."}
        if not existing:
            return {"removed": [], "message": "No apt lock files exist."}

        subprocess.run(["sudo", "rm", "-f", *existing], check=True, capture_output=True, text=True)
        return {"removed": existing, "message": "Stale apt lock files removed."}

    def _read_apt_periodic_config(self) -> Dict[str, bool]:
        path = Path("/etc/apt/apt.conf.d/20auto-upgrades")
        if self.runtime.is_fake or not path.exists():
            return {}
        try:
            text = path.read_text()
        except Exception:
            return {}
        return {
            "update_package_lists": 'APT::Periodic::Update-Package-Lists "1"' in text,
            "unattended_upgrade": 'APT::Periodic::Unattended-Upgrade "1"' in text,
            "autoclean": 'APT::Periodic::AutocleanInterval "7"' in text,
        }

    def get_settings(self) -> Dict[str, Any]:
        system_values = self._read_apt_periodic_config()
        update_lists = self.config_manager.get_value("apt_updates", "update_package_lists", None)
        unattended = self.config_manager.get_value("apt_updates", "unattended_upgrade", None)
        autoclean = self.config_manager.get_value("apt_updates", "autoclean", None)
        return {
            "update_package_lists": self._coerce_bool(update_lists, system_values.get("update_package_lists", False)),
            "unattended_upgrade": self._coerce_bool(unattended, system_values.get("unattended_upgrade", False)),
            "autoclean": self._coerce_bool(autoclean, system_values.get("autoclean", True)),
            "unattended_upgrades_installed": bool(shutil.which("unattended-upgrade")) or self.runtime.is_fake,
        }

    def _coerce_bool(self, value: Optional[str], default: bool) -> bool:
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def save_settings(self, data: Dict[str, Any]) -> Dict[str, Any]:
        settings = {
            "update_package_lists": bool(data.get("update_package_lists")),
            "unattended_upgrade": bool(data.get("unattended_upgrade")),
            "autoclean": bool(data.get("autoclean")),
        }
        for key, value in settings.items():
            self.config_manager.set_value("apt_updates", key, "true" if value else "false")

        if not self.runtime.is_fake:
            self._write_apt_periodic_config(settings)
        return self.get_settings()

    def _write_apt_periodic_config(self, settings: Dict[str, bool]) -> None:
        content = "\n".join([
            f'APT::Periodic::Update-Package-Lists "{1 if settings["update_package_lists"] else 0}";',
            f'APT::Periodic::Unattended-Upgrade "{1 if settings["unattended_upgrade"] else 0}";',
            f'APT::Periodic::AutocleanInterval "{7 if settings["autoclean"] else 0}";',
            "",
        ])
        temp_path = self.runtime.data_dir / "20auto-upgrades"
        temp_path.write_text(content)
        temp_path.chmod(0o644)
        # tee avoids shell redirection and works whether the Flask process is
        # root or is allowed to sudo only this write.
        with temp_path.open("r") as temp_file:
            subprocess.run(
                ["sudo", "tee", "/etc/apt/apt.conf.d/20auto-upgrades"],
                stdin=temp_file,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )

    def get_livepatch_status(self) -> Dict[str, Any]:
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

        result = subprocess.run(
            [binary, "status", "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
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

        fallback = subprocess.run([binary, "status"], capture_output=True, text=True, check=False)
        output = (fallback.stdout or fallback.stderr or result.stderr or "Livepatch status unavailable.").strip()
        return {
            "supported_distro": True,
            "installed": True,
            "enabled": False,
            "status_text": output,
            "details": {},
            "source_url": SUPPORT_SOURCES["livepatch"],
        }

    def _summarize_livepatch_details(self, details: Dict[str, Any]) -> str:
        status = details.get("status") or details.get("Status") or []
        if isinstance(status, list) and status:
            kernel = status[0].get("kernel") or status[0].get("Kernel") or "kernel"
            state = status[0].get("livepatch") or status[0].get("Livepatch") or "status available"
            return f"{kernel}: {state}"
        return "Livepatch status is available."

    def setup_livepatch(self, token: str) -> Dict[str, Any]:
        token = (token or "").strip()
        if not token:
            raise ValueError("Livepatch token is required.")
        distro = self.get_distribution_info()
        if distro["id"] != "ubuntu":
            raise RuntimeError("Ubuntu Livepatch can only be set up on Ubuntu.")
        if self.runtime.is_fake:
            return self.get_livepatch_status()

        binary = shutil.which("canonical-livepatch")
        if not binary:
            if not shutil.which("snap"):
                raise RuntimeError("snap is required to install canonical-livepatch.")
            subprocess.run(["sudo", "snap", "install", "canonical-livepatch"], check=True, capture_output=True, text=True)
            binary = shutil.which("canonical-livepatch") or "/snap/bin/canonical-livepatch"

        subprocess.run(["sudo", binary, "enable", token], check=True, capture_output=True, text=True)
        return self.get_livepatch_status()
