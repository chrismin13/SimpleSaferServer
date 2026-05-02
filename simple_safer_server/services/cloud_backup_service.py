import json
import os
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Optional, Tuple

from simple_safer_server.adapters.command_runner import PIPE, CommandRunner


class CloudBackupService:
    """Keeps Cloud Backup route handlers thin while preserving existing rclone behavior."""

    def __init__(
        self,
        runtime: Any,
        config_manager: Any,
        system_utils: Any,
        task_service: Any,
        logger: Any,
        command_runner: Optional[CommandRunner] = None,
    ) -> None:
        self._runtime = runtime
        self._config_manager = config_manager
        self._system_utils = system_utils
        self._task_service = task_service
        self._logger = logger
        self._command_runner = command_runner or CommandRunner()

    def get_config(self) -> Dict[str, Any]:
        config = self._config_manager.get_all_config()
        backup = config.get("backup", {})
        schedule = config.get("schedule", {})
        response = {
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

    def save_config(self, data: Dict[str, Any]) -> Dict[str, Any]:
        mode = data.get("cloud_mode")
        if mode == "mega":
            result = self._save_mega_config(data)
            if result is not None:
                return result
        elif mode == "advanced":
            result = self._save_advanced_config(data)
            if result is not None:
                return result

        backup_time = data.get("backup_cloud_time")
        bandwidth_limit = data.get("bandwidth_limit")
        if backup_time or bandwidth_limit is not None:
            # Schedule-related values affect generated systemd units, so they
            # must flow through save_schedule before becoming durable config.
            return self.save_schedule(
                {"backup_cloud_time": backup_time, "bandwidth_limit": bandwidth_limit}
            )
        return {"success": True}

    def get_status(self) -> Dict[str, Any]:
        task = self._task_service.get_task("Cloud Backup")
        if not task:
            return {"success": False, "error": "Cloud backup task not found."}
        return {
            "success": True,
            "status": {
                "status": task.status,
                "last_run": task.last_run,
                "next_run": task.next_run,
                "last_run_duration": task.last_run_duration,
            },
        }

    def run_backup(self) -> Dict[str, Any]:
        task = self._task_service.get_task("Cloud Backup")
        if not task:
            return {"success": False, "error": "Cloud backup task not found."}
        task.start()
        return {"success": True}

    def list_mega_folders(self, data: Dict[str, Any]) -> Dict[str, Any]:
        path = data.get("path", "/")
        credentials = self._get_mega_credentials(data)
        if credentials is None:
            return {"success": False, "error": "No MEGA credentials stored."}
        email, obscured_pw = credentials
        config_path = self._write_temp_mega_config(email, obscured_pw)
        try:
            lsjson = self._command_runner.run(
                ["rclone", "lsjson", f"mega:{path}", "--config", config_path],
                capture_output=True,
                text=True,
            )
            if lsjson.returncode != 0:
                error_msg = lsjson.stderr.strip() if lsjson.stderr else "Unknown rclone error"
                self._logger.error("Rclone error listing MEGA folders: %s", error_msg)
                return {"success": False, "error": f"Failed to list MEGA folders: {error_msg}"}
            items = json.loads(lsjson.stdout)
            folders = [item["Name"] for item in items if item["IsDir"]]
            parent = "/".join(path.rstrip("/").split("/")[:-1]) or "/"
            return {"success": True, "folders": folders, "path": path, "parent": parent}
        finally:
            os.remove(config_path)

    def create_mega_folder(self, data: Dict[str, Any]) -> Dict[str, Any]:
        folder_name = (data.get("folder_name") or "").strip()
        path = data.get("path", "/")
        if not folder_name:
            return {"success": False, "error": "Folder name is required."}

        credentials = self._get_mega_credentials(data)
        if credentials is None:
            return {"success": False, "error": "No MEGA credentials stored."}
        email, obscured_pw = credentials
        config_path = self._write_temp_mega_config(email, obscured_pw)
        try:
            full_path = f"{path.rstrip('/')}/{folder_name}" if path != "/" else f"/{folder_name}"
            mkdir = self._command_runner.run(
                ["rclone", "mkdir", f"mega:{full_path}", "--config", config_path],
                capture_output=True,
                text=True,
            )
            if mkdir.returncode != 0:
                error_msg = mkdir.stderr.strip() if mkdir.stderr else "Unknown rclone error"
                self._logger.error("Rclone error creating MEGA folder: %s", error_msg)
                return {"success": False, "error": f"Failed to create folder: {error_msg}"}
            return {"success": True}
        finally:
            os.remove(config_path)

    def get_schedule(self) -> Dict[str, Any]:
        config = self._config_manager.get_all_config()
        schedule = config.get("schedule", {})
        backup = config.get("backup", {})
        return {
            "success": True,
            "backup_cloud_time": schedule.get("backup_cloud_time", ""),
            "bandwidth_limit": backup.get("bandwidth_limit", ""),
        }

    def save_schedule(self, data: Dict[str, Any]) -> Dict[str, Any]:
        backup_time = data.get("backup_cloud_time")
        bandwidth_limit = data.get("bandwidth_limit")

        if self._runtime.is_fake:
            if backup_time:
                self._config_manager.set_value("schedule", "backup_cloud_time", backup_time)
            if bandwidth_limit is not None:
                self._config_manager.set_value("backup", "bandwidth_limit", bandwidth_limit)
            return {"success": True}

        config = self._config_manager.get_all_config()
        if backup_time:
            config.setdefault("schedule", {})["backup_cloud_time"] = backup_time
        if bandwidth_limit is not None:
            config.setdefault("backup", {})["bandwidth_limit"] = bandwidth_limit
        ok, err = self._system_utils.create_systemd_config_file(config)
        if not ok:
            return {"success": False, "error": f"Failed to update systemd config: {err}"}

        ok, err = self._system_utils.install_systemd_services_and_timers(config)
        if not ok:
            return {"success": False, "error": f"Failed to update systemd timers: {err}"}

        if backup_time:
            self._config_manager.set_value("schedule", "backup_cloud_time", backup_time)
        if bandwidth_limit is not None:
            self._config_manager.set_value("backup", "bandwidth_limit", bandwidth_limit)
        return {"success": True}

    def validate_mega(self, data: Dict[str, Any]) -> Dict[str, Any]:
        email = data.get("email")
        password = data.get("password")
        if not email or not password:
            return {"success": False, "error": "Email and password are required."}
        obscured_pw = self._obscure_password(password)
        config_path = self._write_temp_mega_config(email, obscured_pw)
        try:
            lsjson = self._command_runner.run(
                ["rclone", "lsjson", "mega:/", "--config", config_path],
                capture_output=True,
                text=True,
            )
            if lsjson.returncode != 0:
                return {"success": False, "error": "Failed to connect to MEGA. Check credentials."}

            if not self._system_utils.setup_rclone(self._mega_rclone_config(email, obscured_pw)):
                return {"success": False, "error": "Failed to write rclone config for MEGA."}
            self._config_manager.set_value("backup", "cloud_mode", "mega")
            self._config_manager.set_value("backup", "mega_email", email)
            self._config_manager.set_value("backup", "mega_pass", obscured_pw)

            return {"success": True}
        finally:
            os.remove(config_path)

    def _save_mega_config(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        email = data.get("mega_email")
        password = data.get("mega_password")
        folder = data.get("mega_folder")
        if not email or not folder:
            return {"success": False, "error": "Email and folder are required."}

        if password:
            obscured_pw = self._obscure_password(password)
            if not self._system_utils.setup_rclone(self._mega_rclone_config(email, obscured_pw)):
                return {"success": False, "error": "Failed to write rclone config for MEGA."}
            self._config_manager.set_value("backup", "mega_email", email)
            self._config_manager.set_value("backup", "mega_pass", obscured_pw)
        else:
            stored_email = self._config_manager.get_value("backup", "mega_email", "")
            stored_pass = self._config_manager.get_value("backup", "mega_pass", "")
            if not stored_email or not stored_pass:
                return {
                    "success": False,
                    "error": "No MEGA credentials stored. Please provide password.",
                }
            if stored_email != email:
                self._config_manager.set_value("backup", "mega_email", email)
            if not self._system_utils.setup_rclone(self._mega_rclone_config(email, stored_pass)):
                return {"success": False, "error": "Failed to write rclone config for MEGA."}

        self._config_manager.set_value("backup", "cloud_mode", "mega")
        self._config_manager.set_value("backup", "mega_folder", folder)
        self._config_manager.set_value("backup", "rclone_dir", f"mega:{folder}")
        return None

    def _save_advanced_config(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rclone_config = data.get("rclone_config")
        remote_name = data.get("remote_name")
        if not rclone_config or not remote_name:
            return {"success": False, "error": "Rclone config and remote name are required."}
        if not self._system_utils.setup_rclone(rclone_config):
            return {"success": False, "error": "Failed to write rclone config."}
        self._config_manager.set_value("backup", "cloud_mode", "advanced")
        self._config_manager.set_value("backup", "rclone_dir", remote_name)
        return None

    def _get_mega_credentials(self, data: Dict[str, Any]) -> Optional[Tuple[str, str]]:
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
