import json
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Runtime:
    mode: str
    skip_login: bool
    repo_root: Path
    data_dir: Path
    config_dir: Path
    logs_dir: Path
    tasks_log_dir: Path
    rclone_config_dir: Path
    samba_dir: Path
    samba_backup_dir: Path
    systemd_dir: Path
    bin_dir: Path
    backup_drive_dir: Path
    cloud_target_dir: Path
    model_dir: Path
    telemetry_path: Path
    msmtp_config_path: Path
    state_path: Path

    @property
    def is_fake(self) -> bool:
        return self.mode == "fake"

    @property
    def default_mount_point(self) -> str:
        if self.is_fake:
            return str(self.backup_drive_dir)
        return "/media/backup"


class FakeState:
    TASK_NAMES = ["Check Mount", "Drive Health Check", "Cloud Backup"]
    TASK_SERVICE_NAMES = {
        "Check Mount": "check_mount.service",
        "Drive Health Check": "check_health.service",
        "Cloud Backup": "backup_cloud.service",
    }

    def __init__(self, runtime: Runtime):
        self.runtime = runtime
        self._lock = threading.RLock()
        self._ensure_layout()

    def _ensure_layout(self) -> None:
        self.runtime.data_dir.mkdir(parents=True, exist_ok=True)
        self.runtime.config_dir.mkdir(parents=True, exist_ok=True)
        self.runtime.logs_dir.mkdir(parents=True, exist_ok=True)
        self.runtime.tasks_log_dir.mkdir(parents=True, exist_ok=True)
        self.runtime.rclone_config_dir.mkdir(parents=True, exist_ok=True)
        self.runtime.samba_dir.mkdir(parents=True, exist_ok=True)
        self.runtime.samba_backup_dir.mkdir(parents=True, exist_ok=True)
        self.runtime.systemd_dir.mkdir(parents=True, exist_ok=True)
        self.runtime.bin_dir.mkdir(parents=True, exist_ok=True)
        self.runtime.backup_drive_dir.mkdir(parents=True, exist_ok=True)
        self.runtime.cloud_target_dir.mkdir(parents=True, exist_ok=True)
        if not self.runtime.state_path.exists():
            self.save(self.default_state())

    def default_state(self) -> dict[str, Any]:
        return {
            "mounted": False,
            "mount_point": str(self.runtime.backup_drive_dir),
            "selected_drive": "/dev/fakebackup1",
            "uuid": "FAKE-UUID-0001",
            "usb_id": "FAKE:0001",
            "smb_services": {"smbd": "active", "nmbd": "active"},
            "tasks": {
                task_name: {
                    "status": "Not Run Yet",
                    "last_run": "",
                    "last_run_duration": "-",
                    "log": "",
                }
                for task_name in self.TASK_NAMES
            },
        }

    def load(self) -> dict[str, Any]:
        try:
            return json.loads(self.runtime.state_path.read_text())
        except Exception:
            state = self.default_state()
            self.save(state)
            return state

    def _write_state(self, state: dict[str, Any]) -> None:
        """Write state atomically via a unique temp file and rename to avoid partial writes."""
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.runtime.state_path.parent,
            prefix=f"{self.runtime.state_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp_file:
            json.dump(state, tmp_file, indent=2)
            tmp_path = Path(tmp_file.name)
        tmp_path.replace(self.runtime.state_path)

    def save(self, state: dict[str, Any]) -> None:
        with self._lock:
            self._write_state(state)

    def get_virtual_drives(self) -> list[dict[str, Any]]:
        state = self.load()
        mount_point = state.get("mount_point", str(self.runtime.backup_drive_dir))
        partition_mount = mount_point if state.get("mounted") else ""
        return [
            {
                "path": "/dev/fakebackup",
                "model": "Fake Developer Backup Drive",
                "size": "Local Folder",
                "type": "usb",
                "partitions": [
                    {
                        "path": state.get("selected_drive", "/dev/fakebackup1"),
                        "type": "ntfs",
                        "label": "DEV_BACKUP",
                        "size": "Local Folder",
                        "mountpoint": partition_mount,
                    }
                ],
            }
        ]

    def set_mount(self, mounted: bool, mount_point: str | None = None, drive: str | None = None) -> None:
        with self._lock:
            state = self.load()
            state["mounted"] = mounted
            if mount_point:
                state["mount_point"] = mount_point
            if drive:
                state["selected_drive"] = drive
            self.save(state)

    def is_mounted(self, mount_point: str | None = None) -> bool:
        state = self.load()
        if mount_point and state.get("mount_point") != mount_point:
            return False
        return bool(state.get("mounted"))

    def get_mount_point(self) -> str:
        return self.load().get("mount_point", str(self.runtime.backup_drive_dir))

    def set_smb_services(self, smbd: str, nmbd: str) -> None:
        with self._lock:
            state = self.load()
            state["smb_services"] = {"smbd": smbd, "nmbd": nmbd}
            self.save(state)

    def get_smb_services(self) -> dict[str, str]:
        return self.load().get("smb_services", {"smbd": "active", "nmbd": "active"})

    def set_task_state(
        self,
        task_name: str,
        *,
        status: str | None = None,
        last_run: str | None = None,
        last_run_duration: str | None = None,
        log: str | None = None,
    ) -> None:
        with self._lock:
            state = self.load()
            task_state = state.setdefault("tasks", {}).setdefault(task_name, {})
            if status is not None:
                task_state["status"] = status
            if last_run is not None:
                task_state["last_run"] = last_run
            if last_run_duration is not None:
                task_state["last_run_duration"] = last_run_duration
            if log is not None:
                task_state["log"] = log
            self.save(state)

    def append_task_log(self, task_name: str, message: str) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            state = self.load()
            task_state = state.setdefault("tasks", {}).setdefault(task_name, {})
            current = task_state.get("log", "")
            task_state["log"] = f"{current}{now} {message}\n"
            self.save(state)
            log_path = self.runtime.tasks_log_dir / f"{task_name.lower().replace(' ', '_')}.log"
            log_path.write_text(task_state["log"])

    def get_task_log(self, task_name: str) -> str:
        state = self.load()
        task_state = state.setdefault("tasks", {}).setdefault(task_name, {})
        return task_state.get("log", "") or "No logs yet."

    def get_task_state(self, task_name: str) -> dict[str, Any]:
        state = self.load()
        return state.setdefault("tasks", {}).setdefault(
            task_name,
            {"status": "Not Run Yet", "last_run": "", "last_run_duration": "-", "log": ""},
        )

    def get_next_run(self, task_name: str, backup_time: str) -> str:
        try:
            backup_hour, backup_minute = [int(part) for part in backup_time.split(":", 1)]
        except Exception:
            backup_hour, backup_minute = 3, 0

        offsets = {
            "Check Mount": -2,
            "Drive Health Check": -1,
            "Cloud Backup": 0,
        }
        offset = offsets.get(task_name, 0)
        next_run = datetime.now().replace(hour=backup_hour, minute=backup_minute, second=0, microsecond=0)
        next_run += timedelta(minutes=offset)
        if next_run <= datetime.now():
            next_run += timedelta(days=1)
        return next_run.strftime("%Y-%m-%d %H:%M:%S")


_runtime: Runtime | None = None
_fake_state: FakeState | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def get_runtime() -> Runtime:
    global _runtime
    if _runtime is not None:
        return _runtime

    repo_root = _repo_root()
    mode = os.environ.get("SSS_MODE", "real").strip().lower() or "real"

    if mode == "fake":
        data_dir = repo_root / ".dev-data"
        skip_login = os.environ.get("SSS_SKIP_LOGIN", "false").strip().lower() in {"1", "true", "yes", "on"}
        _runtime = Runtime(
            mode="fake",
            skip_login=skip_login,
            repo_root=repo_root,
            data_dir=data_dir,
            config_dir=data_dir / "config",
            logs_dir=data_dir / "logs",
            tasks_log_dir=data_dir / "logs" / "tasks",
            rclone_config_dir=data_dir / "rclone",
            samba_dir=data_dir / "samba",
            samba_backup_dir=data_dir / "samba" / "backups",
            systemd_dir=data_dir / "systemd",
            bin_dir=data_dir / "bin",
            backup_drive_dir=data_dir / "backup-drive",
            cloud_target_dir=data_dir / "cloud-target",
            model_dir=repo_root / "harddrive_model",
            telemetry_path=data_dir / "telemetry.csv",
            msmtp_config_path=data_dir / "msmtprc",
            state_path=data_dir / "state.json",
        )
    else:
        _runtime = Runtime(
            mode="real",
            skip_login=False,
            repo_root=repo_root,
            data_dir=Path("/opt/SimpleSaferServer"),
            config_dir=Path("/etc/SimpleSaferServer"),
            logs_dir=Path("/var/log/SimpleSaferServer"),
            tasks_log_dir=Path("/var/log/SimpleSaferServer"),
            rclone_config_dir=Path.home() / ".config" / "rclone",
            samba_dir=Path("/etc/samba"),
            samba_backup_dir=Path("/etc/samba/backups"),
            systemd_dir=Path("/etc/systemd/system"),
            bin_dir=Path("/usr/local/bin"),
            backup_drive_dir=Path("/media/backup"),
            cloud_target_dir=Path("/media/backup"),
            model_dir=Path("/opt/SimpleSaferServer/harddrive_model"),
            telemetry_path=repo_root / "telemetry.csv",
            msmtp_config_path=Path("/etc/msmtprc"),
            state_path=Path("/tmp/simple_safer_server_unused_state.json"),
        )

    if _runtime.is_fake:
        get_fake_state()

    return _runtime


def get_fake_state() -> FakeState:
    global _fake_state
    if _fake_state is None:
        _fake_state = FakeState(get_runtime())
    return _fake_state
