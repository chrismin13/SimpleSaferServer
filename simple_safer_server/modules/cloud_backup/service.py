import json
import os
import re
from dataclasses import dataclass
from tempfile import NamedTemporaryFile
from typing import Any

from simple_safer_server.adapters.command_runner import PIPE, CommandRunner
from simple_safer_server.core.ownership import record_runtime_owned_resource
from simple_safer_server.core.privileged_client import (
    PrivilegedActionClient,
    PrivilegedActionClientError,
)
from simple_safer_server.services.file_persistence import atomic_write_text
from simple_safer_server.services.schedule_time import (
    ScheduleTimeError,
    normalize_ui_schedule_time,
)
from simple_safer_server.web.i18n import gettext
from simple_safer_server.web.problems import NotFoundProblem, OperationProblem, ValidationProblem


@dataclass(frozen=True)
class CloudBackupStatus:
    status: str
    last_run: str
    next_run: str
    last_run_duration: str


@dataclass(frozen=True)
class MegaFolderList:
    folders: list[str]
    path: str
    parent: str


BANDWIDTH_LIMIT_RE = re.compile(r"^\d+(?:k|M|G)$", re.IGNORECASE)
RCLONE_ADMIN_TIMEOUT_SECONDS = 60


def strict_cloud_enabled(value: Any) -> bool:
    """Return the explicit cloud-backup setting or raise on missing/invalid config."""
    text = "" if value is None else str(value).strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    raise ValidationProblem(
        gettext(
            "Cloud backup enabled setting is missing or invalid. Save Cloud Backup settings again."
        )
    )


def normalize_bandwidth_limit(value: Any) -> str:
    """Return a safe rclone bwlimit value or raise a validation problem."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if not BANDWIDTH_LIMIT_RE.match(text):
        raise ValidationProblem(gettext("Bandwidth limit must look like 512k, 4M, or 1G."))
    return text


class CloudBackupService:
    """Keeps Cloud Backup route handlers thin while preserving existing rclone behavior."""

    def __init__(
        self,
        runtime: Any,
        config_manager: Any,
        system_utils: Any,
        task_service: Any,
        logger: Any,
        command_runner: CommandRunner | None = None,
        privileged_actions: PrivilegedActionClient | None = None,
    ) -> None:
        self._runtime = runtime
        self._config_manager = config_manager
        self._system_utils = system_utils
        self._task_service = task_service
        self._logger = logger
        self._command_runner = command_runner or CommandRunner()
        self._privileged_actions = privileged_actions or PrivilegedActionClient()

    def get_config(self) -> dict[str, Any]:
        config = self._config_manager.get_all_config()
        backup = config.get("backup", {})
        schedule = config.get("schedule", {})
        response = {
            "cloud_enabled": backup.get("cloud_enabled", "false"),
            "cloud_mode": backup.get("cloud_mode", ""),
            "mega_email": backup.get("mega_email", ""),
            "mega_folder": backup.get("mega_folder", ""),
            "rclone_dir": backup.get("rclone_dir", ""),
            "bandwidth_limit": backup.get("bandwidth_limit", ""),
            "backup_cloud_time": schedule.get("backup_cloud_time", ""),
        }
        rclone_conf_path = self._runtime.rclone_config_dir / "rclone.conf"
        if os.path.exists(rclone_conf_path):
            with open(rclone_conf_path) as config_file:
                response["rclone_config"] = config_file.read()
        else:
            response["rclone_config"] = ""
        return response

    def save_config(self, data: dict[str, Any]) -> dict[str, Any]:
        cloud_enabled: bool | None = None
        if data.get("cloud_enabled") is not None:
            cloud_enabled = strict_cloud_enabled(data.get("cloud_enabled"))
        mode = data.get("cloud_mode")
        if mode == "mega":
            self._save_mega_config(data)
        elif mode == "advanced":
            self._save_advanced_config(data)
        if cloud_enabled is not None:
            self._config_manager.set_value(
                "backup",
                "cloud_enabled",
                str(cloud_enabled).lower(),
            )

        backup_time = data.get("backup_cloud_time")
        bandwidth_limit = data.get("bandwidth_limit")
        if backup_time or bandwidth_limit is not None:
            return self.save_schedule(
                {"backup_cloud_time": backup_time, "bandwidth_limit": bandwidth_limit}
            )
        return {}

    def get_status(self) -> CloudBackupStatus:
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
                gettext("Cloud backup task not found."),
                title=gettext("Cloud Backup task not found"),
                slug="cloud-backup-task-not-found",
            )
        return CloudBackupStatus(
            status=task.status,
            last_run=task.last_run,
            next_run=task.next_run,
            last_run_duration=task.last_run_duration,
        )

    def run_backup(self) -> None:
        if not strict_cloud_enabled(
            self._config_manager.get_value("backup", "cloud_enabled", None)
        ):
            raise ValidationProblem(gettext("Cloud backup is disabled."))
        task = self._task_service.get_task("Cloud Backup")
        if not task:
            raise NotFoundProblem(
                gettext("Cloud backup task not found."),
                title=gettext("Cloud Backup task not found"),
                slug="cloud-backup-task-not-found",
            )
        task.start()

    def list_mega_folders(self, data: dict[str, Any]) -> MegaFolderList:
        path = data.get("path", "/")
        credentials = self._get_mega_credentials(data)
        if credentials is None:
            raise ValidationProblem(
                gettext("No MEGA credentials stored."),
                title=gettext("Missing MEGA credentials"),
                slug="cloud-backup-missing-mega-credentials",
            )
        email, obscured_pw = credentials
        config_path = self._write_temp_mega_config(email, obscured_pw)
        try:
            lsjson = self._command_runner.run(
                ["rclone", "lsjson", f"mega:{path}", "--config", config_path],
                capture_output=True,
                text=True,
                timeout=RCLONE_ADMIN_TIMEOUT_SECONDS,
            )
            if lsjson.returncode != 0:
                error_msg = (
                    lsjson.stderr.strip() if lsjson.stderr else gettext("Unknown rclone error")
                )
                self._logger.error("Rclone error listing MEGA folders: %s", error_msg)
                raise OperationProblem(
                    gettext("Failed to list MEGA folders: {error}").format(error=error_msg),
                    title=gettext("Cloud Backup rclone error"),
                    slug="cloud-backup-rclone-error",
                )
            items = json.loads(lsjson.stdout)
            folders = [item["Name"] for item in items if item["IsDir"]]
            parent = "/".join(path.rstrip("/").split("/")[:-1]) or "/"
            return MegaFolderList(folders=folders, path=path, parent=parent)
        finally:
            os.remove(config_path)

    def create_mega_folder(self, data: dict[str, Any]) -> None:
        folder_name = (data.get("folder_name") or "").strip()
        path = data.get("path", "/")
        if not folder_name:
            raise ValidationProblem(gettext("Folder name is required."))

        credentials = self._get_mega_credentials(data)
        if credentials is None:
            raise ValidationProblem(
                gettext("No MEGA credentials stored."),
                title=gettext("Missing MEGA credentials"),
                slug="cloud-backup-missing-mega-credentials",
            )
        email, obscured_pw = credentials
        config_path = self._write_temp_mega_config(email, obscured_pw)
        try:
            full_path = f"{path.rstrip('/')}/{folder_name}" if path != "/" else f"/{folder_name}"
            mkdir = self._command_runner.run(
                ["rclone", "mkdir", f"mega:{full_path}", "--config", config_path],
                capture_output=True,
                text=True,
                timeout=RCLONE_ADMIN_TIMEOUT_SECONDS,
            )
            if mkdir.returncode != 0:
                error_msg = mkdir.stderr.strip() if mkdir.stderr else gettext("Unknown rclone error")
                self._logger.error("Rclone error creating MEGA folder: %s", error_msg)
                raise OperationProblem(
                    gettext("Failed to create folder: {error}").format(error=error_msg),
                    title=gettext("Cloud Backup rclone error"),
                    slug="cloud-backup-rclone-error",
                )
        finally:
            os.remove(config_path)

    def get_schedule(self) -> dict[str, Any]:
        config = self._config_manager.get_all_config()
        schedule = config.get("schedule", {})
        backup = config.get("backup", {})
        return {
            "backup_cloud_time": schedule.get("backup_cloud_time", ""),
            "bandwidth_limit": backup.get("bandwidth_limit", ""),
        }

    def save_schedule(self, data: dict[str, Any]) -> dict[str, Any]:
        backup_time = data.get("backup_cloud_time")
        has_bandwidth_limit = "bandwidth_limit" in data
        bandwidth_limit = normalize_bandwidth_limit(data.get("bandwidth_limit"))
        if backup_time:
            try:
                backup_time = normalize_ui_schedule_time(backup_time)
            except ScheduleTimeError as exc:
                raise ValidationProblem(str(exc)) from exc

        if backup_time:
            self._config_manager.set_value("schedule", "backup_cloud_time", backup_time)
            self._config_manager.set_value("schedule", "configured", "true")
        if has_bandwidth_limit:
            self._config_manager.set_value("backup", "bandwidth_limit", bandwidth_limit)
        return {}

    def validate_mega(self, data: dict[str, Any]) -> None:
        email = data.get("email")
        password = data.get("password")
        if not email or not password:
            raise ValidationProblem(gettext("Email and password are required."))
        obscured_pw = self._obscure_password(password)
        config_path = self._write_temp_mega_config(email, obscured_pw)
        try:
            lsjson = self._command_runner.run(
                ["rclone", "lsjson", "mega:/", "--config", config_path],
                capture_output=True,
                text=True,
                timeout=RCLONE_ADMIN_TIMEOUT_SECONDS,
            )
            if lsjson.returncode != 0:
                raise ValidationProblem(gettext("Failed to connect to MEGA. Check credentials."))

            self._write_managed_rclone_config(
                self._mega_rclone_config(email, obscured_pw),
                gettext("Failed to write rclone config for MEGA."),
            )
            self._config_manager.set_value("backup", "cloud_mode", "mega")
            self._config_manager.set_value("backup", "mega_email", email)
            self._config_manager.set_value("backup", "mega_pass", obscured_pw)

        finally:
            os.remove(config_path)

    def _save_mega_config(self, data: dict[str, Any]) -> None:
        email = data.get("mega_email")
        password = data.get("mega_password")
        folder = data.get("mega_folder")
        if not email or not folder:
            raise ValidationProblem(gettext("Email and folder are required."))

        if password:
            obscured_pw = self._obscure_password(password)
            self._write_managed_rclone_config(
                self._mega_rclone_config(email, obscured_pw),
                gettext("Failed to write rclone config for MEGA."),
            )
            self._config_manager.set_value("backup", "mega_email", email)
            self._config_manager.set_value("backup", "mega_pass", obscured_pw)
        else:
            stored_email = self._config_manager.get_value("backup", "mega_email", "")
            stored_pass = self._config_manager.get_value("backup", "mega_pass", "")
            if not stored_email or not stored_pass:
                raise ValidationProblem(
                    gettext("No MEGA credentials stored. Please provide password."),
                    title=gettext("Missing MEGA credentials"),
                    slug="cloud-backup-missing-mega-credentials",
                )
            self._write_managed_rclone_config(
                self._mega_rclone_config(email, stored_pass),
                gettext("Failed to write rclone config for MEGA."),
            )
            if stored_email != email:
                self._config_manager.set_value("backup", "mega_email", email)

        self._config_manager.set_value("backup", "cloud_mode", "mega")
        self._config_manager.set_value("backup", "mega_folder", folder)
        self._config_manager.set_value("backup", "rclone_dir", f"mega:{folder}")
        self._config_manager.set_value("backup", "cloud_enabled", "true")
        self._config_manager.set_value("backup", "cloud_skipped", "false")

    def _save_advanced_config(self, data: dict[str, Any]) -> None:
        rclone_config = data.get("rclone_config")
        remote_name = data.get("remote_name")
        if not rclone_config or not remote_name:
            raise ValidationProblem(gettext("Rclone config and remote name are required."))
        self._write_managed_rclone_config(
            rclone_config,
            gettext("Failed to write rclone config."),
        )
        self._config_manager.set_value("backup", "cloud_mode", "advanced")
        self._config_manager.set_value("backup", "rclone_dir", remote_name)
        self._config_manager.set_value("backup", "cloud_enabled", "true")
        self._config_manager.set_value("backup", "cloud_skipped", "false")

    def _write_managed_rclone_config(self, rclone_config: str, failure_message: str) -> None:
        if self._runtime.is_fake:
            config_path = self._runtime.rclone_config_dir / "rclone.conf"
            try:
                atomic_write_text(config_path, rclone_config, mode=0o600)
                record_runtime_owned_resource(
                    self._runtime,
                    "cloud-backup",
                    kind="config-file",
                    identifier=str(config_path),
                    reason="Keep SSS cloud backup separate from root's global rclone config.",
                )
            except OSError as exc:
                raise OperationProblem(
                    failure_message,
                    slug="cloud-backup-rclone-config-write-failed",
                ) from exc
            return

        try:
            self._privileged_actions.run(
                "cloud-backup.write-rclone-config",
                {"rclone_config": rclone_config},
            )
        except PrivilegedActionClientError as exc:
            self._logger.error("Privileged rclone config write failed: %s", exc)
            raise OperationProblem(
                failure_message,
                slug="cloud-backup-rclone-config-write-failed",
            ) from exc

    def _get_mega_credentials(self, data: dict[str, Any]) -> tuple[str, str] | None:
        email = data.get("email")
        password = data.get("password")
        if email and password:
            return email, self._obscure_password(password)

        email = self._config_manager.get_value("backup", "mega_email", "")
        obscured_pw = self._config_manager.get_value("backup", "mega_pass", "")
        self._logger.info("Using stored credentials for cloud backup")
        if not email or not obscured_pw:
            return None
        return email, obscured_pw

    def _obscure_password(self, password: str) -> str:
        result = self._command_runner.run(
            ["rclone", "obscure", "-"],
            input=f"{password}\n",
            stdout=PIPE,
            check=True,
            text=True,
            timeout=RCLONE_ADMIN_TIMEOUT_SECONDS,
        )
        return result.stdout.strip()

    def _write_temp_mega_config(self, email: str, obscured_pw: str) -> str:
        # rclone needs a file path for list/validation commands, but this
        # transient config is not the managed root rclone.conf. delete=False
        # lets callers pass the path to rclone; callers remove it after use.
        with NamedTemporaryFile(
            delete=False, mode="w", prefix="rclone-", suffix=".conf"
        ) as config_file:
            config_file.write(self._mega_rclone_config(email, obscured_pw))
            return config_file.name

    def _mega_rclone_config(self, email: str, obscured_pw: str) -> str:
        # rclone stores MEGA passwords in obscured form, so every temporary or
        # managed config path receives the output of rclone obscure, not raw input.
        return f"""[mega]\ntype = mega\nuser = {email}\npass = {obscured_pw}\n"""
