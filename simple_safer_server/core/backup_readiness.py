from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from simple_safer_server.modules.alerts.smtp_mailer import read_runtime_smtp_config
from simple_safer_server.services.schedule_time import (
    ScheduleTimeError,
    normalize_ui_schedule_time,
)
from simple_safer_server.web.i18n import gettext

STATUS_COMPLETE = "complete"
STATUS_INCOMPLETE = "incomplete"
STATUS_SKIPPED = "skipped"


@dataclass(frozen=True)
class BackupReadinessItem:
    key: str
    title: str
    detail: str
    status: str
    action_label: str
    action_url: str
    required: bool = True

    @property
    def complete(self) -> bool:
        return self.status == STATUS_COMPLETE

    @property
    def status_label(self) -> str:
        _ = gettext
        if self.complete:
            return _("Complete")
        if self.status == STATUS_SKIPPED:
            return _("Skipped")
        return _("Incomplete")

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "detail": self.detail,
            "status": self.status,
            "status_label": self.status_label,
            "complete": self.complete,
            "action_label": self.action_label,
            "action_url": self.action_url,
            "required": self.required,
        }


@dataclass(frozen=True)
class BackupReadiness:
    status: str
    title: str
    detail: str
    completed_required_count: int
    required_count: int
    items: tuple[BackupReadinessItem, ...]

    @property
    def complete(self) -> bool:
        return self.status == STATUS_COMPLETE

    @property
    def count_label(self) -> str:
        _ = gettext
        return _("{completed} of {required} complete").format(
            completed=self.completed_required_count,
            required=self.required_count,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "complete": self.complete,
            "title": self.title,
            "detail": self.detail,
            "completed_required_count": self.completed_required_count,
            "required_count": self.required_count,
            "count_label": self.count_label,
            "items": [item.as_dict() for item in self.items],
        }


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() == "true"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _storage_item(config: dict[str, dict[str, str]]) -> BackupReadinessItem:
    storage = config.get("storage", {})
    mode = _text(storage.get("mode"))
    path = _text(storage.get("path"))
    storage_id = _text(storage.get("storage_id"))
    if mode in {"existing_folder", "managed_drive"} and path and storage_id:
        return BackupReadinessItem(
            key="storage",
            title="Choose backup storage",
            detail=f"Backup data is stored at {path}.",
            status=STATUS_COMPLETE,
            action_label="Open Storage",
            action_url="/storage",
        )
    return BackupReadinessItem(
        key="storage",
        title="Choose backup storage",
        detail="Choose an existing folder or set up a managed drive before backups run.",
        status=STATUS_INCOMPLETE,
        action_label="Choose Storage",
        action_url="/setup#step2",
    )


def _network_access_item(smb_manager: Any | None) -> BackupReadinessItem:
    if smb_manager is None:
        return BackupReadinessItem(
            key="network_access",
            title="Enable local network backup access",
            detail="Set up the managed backup share so computers can copy files to the server.",
            status=STATUS_INCOMPLETE,
            action_label="Open File Sharing",
            action_url="/network_file_sharing",
        )

    try:
        shares = smb_manager.list_managed_shares()
    except Exception as exc:
        return BackupReadinessItem(
            key="network_access",
            title="Enable local network backup access",
            detail=f"Could not inspect the managed backup share: {exc}",
            status=STATUS_INCOMPLETE,
            action_label="Open File Sharing",
            action_url="/network_file_sharing",
        )

    backup_share = next((share for share in shares if share.get("name") == "backup"), None)
    if backup_share:
        return BackupReadinessItem(
            key="network_access",
            title="Enable local network backup access",
            detail=f"The managed backup share points at {backup_share.get('path', 'storage')}.",
            status=STATUS_COMPLETE,
            action_label="Open File Sharing",
            action_url="/network_file_sharing",
        )
    return BackupReadinessItem(
        key="network_access",
        title="Enable local network backup access",
        detail="Create or repair the managed backup share so computers can reach the server.",
        status=STATUS_INCOMPLETE,
        action_label="Open File Sharing",
        action_url="/network_file_sharing",
    )


def _cloud_backup_item(config: dict[str, dict[str, str]]) -> BackupReadinessItem:
    backup = config.get("backup", {})
    if _truthy(backup.get("cloud_enabled")) and _text(backup.get("rclone_dir")):
        return BackupReadinessItem(
            key="cloud_backup",
            title="Set up cloud backup",
            detail=f"Cloud backup is configured for {_text(backup.get('rclone_dir'))}.",
            status=STATUS_COMPLETE,
            action_label="Open Cloud Backup",
            action_url="/cloud_backup",
        )
    if _truthy(backup.get("cloud_skipped")):
        return BackupReadinessItem(
            key="cloud_backup",
            title="Set up cloud backup",
            detail="Cloud backup was skipped, so this server does not yet have an off-site SSS copy.",
            status=STATUS_SKIPPED,
            action_label="Set Up Cloud Backup",
            action_url="/cloud_backup",
        )
    return BackupReadinessItem(
        key="cloud_backup",
        title="Set up cloud backup",
        detail="Choose a cloud destination so the backup has an off-site copy.",
        status=STATUS_INCOMPLETE,
        action_label="Set Up Cloud Backup",
        action_url="/setup#step4",
    )


def _alerts_item(config: dict[str, dict[str, str]], runtime: Any | None) -> BackupReadinessItem:
    backup = config.get("backup", {})
    smtp_config = read_runtime_smtp_config(runtime) if runtime is not None else {}
    required_smtp = ("smtp_server", "smtp_port", "smtp_username", "smtp_password")
    has_smtp = all(_text(smtp_config.get(key)) for key in required_smtp)
    has_addresses = _text(backup.get("email_address")) and (
        _text(backup.get("from_address")) or _text(smtp_config.get("from_address"))
    )
    if has_smtp and has_addresses:
        return BackupReadinessItem(
            key="alerts",
            title="Configure alerts",
            detail=f"Alerts are sent to {_text(backup.get('email_address'))}.",
            status=STATUS_COMPLETE,
            action_label="Open Alerts",
            action_url="/alerts",
        )
    return BackupReadinessItem(
        key="alerts",
        title="Configure alerts",
        detail="Add SMTP settings and an alert email address so backup problems are not silent.",
        status=STATUS_INCOMPLETE,
        action_label="Configure Alerts",
        action_url="/setup#step5",
    )


def _schedule_item(config: dict[str, dict[str, str]]) -> BackupReadinessItem:
    schedule = config.get("schedule", {})
    backup_time = _text(schedule.get("backup_cloud_time"))
    configured = _truthy(schedule.get("configured"))
    if configured and backup_time:
        try:
            normalized = normalize_ui_schedule_time(backup_time)
        except ScheduleTimeError:
            pass
        else:
            return BackupReadinessItem(
                key="schedule",
                title="Choose backup schedule",
                detail=f"Backup jobs are scheduled around {normalized}.",
                status=STATUS_COMPLETE,
                action_label="Open Cloud Backup",
                action_url="/cloud_backup",
            )
    return BackupReadinessItem(
        key="schedule",
        title="Choose backup schedule",
        detail="Choose when the server should run backup-related jobs.",
        status=STATUS_INCOMPLETE,
        action_label="Choose Schedule",
        action_url="/setup#step6",
    )


def build_backup_readiness(
    config_manager: Any,
    *,
    runtime: Any | None = None,
    smb_manager: Any | None = None,
) -> BackupReadiness:
    """Build the shared first-run and dashboard backup-protection checklist."""
    if hasattr(config_manager, "load_config"):
        config_manager.load_config()
    config = config_manager.get_all_config()
    items = (
        _storage_item(config),
        _network_access_item(smb_manager),
        _cloud_backup_item(config),
        _alerts_item(config, runtime),
        _schedule_item(config),
    )
    required_items = [item for item in items if item.required]
    completed_required_count = sum(1 for item in required_items if item.complete)
    required_count = len(required_items)
    if completed_required_count == required_count:
        status = STATUS_COMPLETE
        title = "Backup protection is ready"
        detail = "Storage, local access, cloud backup, alerts, and schedule are configured."
    else:
        status = STATUS_INCOMPLETE
        title = "Backup protection needs setup"
        detail = "Finish the checklist so the server has a safer backup setup."

    return BackupReadiness(
        status=status,
        title=title,
        detail=detail,
        completed_required_count=completed_required_count,
        required_count=required_count,
        items=items,
    )
