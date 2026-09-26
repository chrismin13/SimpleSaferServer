import re
import threading
from dataclasses import dataclass
from typing import Any

from simple_safer_server.services.schedule_time import (
    ScheduleTimeError,
    normalize_ui_schedule_time,
)
from simple_safer_server.web.problems import (
    ApiProblem,
    NotFoundProblem,
    OperationProblem,
    ValidationProblem,
)


@dataclass(frozen=True)
class CloudBackupStatus:
    status: str
    last_run: str
    next_run: str
    last_run_duration: str


BANDWIDTH_LIMIT_RE = re.compile(r"^\d+(?:k|M|G)$", re.IGNORECASE)


def strict_cloud_enabled(value: Any) -> bool:
    """Return the explicit cloud-backup setting or raise on missing/invalid config."""
    text = "" if value is None else str(value).strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    raise ValidationProblem(
        "Cloud backup enabled setting is missing or invalid. Save Cloud Backup settings again."
    )


def normalize_bandwidth_limit(value: Any) -> str:
    """Return a safe rclone bwlimit value or raise a validation problem."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if not BANDWIDTH_LIMIT_RE.match(text):
        raise ValidationProblem("Bandwidth limit must look like 512k, 4M, or 1G.")
    return text


class CloudBackupService:
    """Manage backup scheduling and runs; connection credentials belong to the editor."""

    def __init__(
        self,
        runtime: Any,
        config_manager: Any,
        system_utils: Any,
        task_service: Any,
    ) -> None:
        self._runtime = runtime
        self._config_manager = config_manager
        self._system_utils = system_utils
        self._task_service = task_service
        self._settings_lock = threading.RLock()

    def get_config(self) -> dict[str, Any]:
        """Public backup settings; the dedicated rclone editor owns credentials."""
        self._config_manager.load_config()
        config = self._config_manager.get_all_config()
        backup = config.get("backup", {})
        return {
            "cloud_enabled": backup.get("cloud_enabled", "false"),
            "rclone_dir": backup.get("rclone_dir", ""),
            **self.get_schedule(),
        }

    def save_destination(self, destination: str, enabled: bool) -> dict[str, Any]:
        """Publish backup settings while the caller holds the rclone config lock."""
        with self._settings_lock:
            return self._save_settings(
                {}, {"rclone_dir": destination, "cloud_enabled": str(enabled).lower()}
            )

    def get_status(self) -> CloudBackupStatus:
        self._config_manager.load_config()
        if not strict_cloud_enabled(
            self._config_manager.get_value("backup", "cloud_enabled", None)
        ):
            return CloudBackupStatus(
                status="Disabled",
                last_run="—",
                next_run="—",
                last_run_duration="—",
            )
        task = self._task_service.get_task("Cloud Backup")
        if not task:
            raise NotFoundProblem(
                "Cloud backup task not found.",
                title="Cloud Backup task not found",
                slug="cloud-backup-task-not-found",
            )
        return CloudBackupStatus(
            status=task.status,
            last_run=task.last_run,
            next_run=task.next_run,
            last_run_duration=task.last_run_duration,
        )

    def run_backup(self) -> None:
        self._config_manager.load_config()
        if not strict_cloud_enabled(
            self._config_manager.get_value("backup", "cloud_enabled", None)
        ):
            raise ValidationProblem("Cloud backup is disabled.")
        task = self._task_service.get_task("Cloud Backup")
        if not task:
            raise NotFoundProblem(
                "Cloud backup task not found.",
                title="Cloud Backup task not found",
                slug="cloud-backup-task-not-found",
            )
        task.start()

    def get_schedule(self) -> dict[str, Any]:
        self._config_manager.load_config()
        config = self._config_manager.get_all_config()
        schedule = config.get("schedule", {})
        backup = config.get("backup", {})
        return {
            "backup_cloud_time": schedule.get("backup_cloud_time", ""),
            "bandwidth_limit": backup.get("bandwidth_limit", ""),
        }

    def save_schedule(self, data: dict[str, Any]) -> dict[str, Any]:
        # A failing timer update must not roll back a concurrent editor save.
        with self._settings_lock:
            return self._save_settings(data, {})

    def _save_settings(
        self, data: dict[str, Any], backup_changes: dict[str, str]
    ) -> dict[str, Any]:
        backup_time = data.get("backup_cloud_time")
        if backup_time:
            try:
                backup_time = normalize_ui_schedule_time(backup_time)
            except ScheduleTimeError as exc:
                raise ValidationProblem(str(exc)) from exc
        if "bandwidth_limit" in data:
            backup_changes["bandwidth_limit"] = normalize_bandwidth_limit(data["bandwidth_limit"])
        self._config_manager.load_config()
        previous = self._config_manager.get_all_config()
        changes = {"backup": backup_changes}
        if backup_time:
            changes["schedule"] = {"backup_cloud_time": backup_time}
        # Keep unrelated settings fresh; destination and enabled must be one
        # write so a scheduled backup never observes half a selection.
        self._config_manager.update_values(changes)
        config = self._config_manager.get_all_config()
        try:
            setup_complete = str(config.get("system", {}).get("setup_complete", "false")).lower()
            # First-run setup has not chosen a schedule yet. Its completion
            # transaction installs all units once the required fields exist.
            if not self._runtime.is_fake and setup_complete == "true":
                ok, err = self._system_utils.install_systemd_services_and_timers(
                    config, activate_timers=True
                )
                if not ok:
                    raise OperationProblem(f"Failed to update systemd timers: {err}")
        except ApiProblem, OSError:
            rollback = {
                section: {key: previous.get(section, {}).get(key, "") for key in values}
                for section, values in changes.items()
            }
            self._config_manager.update_values(rollback)
            raise
        return {}
