from datetime import datetime
from typing import Any, Dict, List, Optional

from simple_safer_server.services.file_persistence import locked_json_update, read_json

DISABLED_TIMERS_FILENAME = "disabled_timers.json"
RESTORE_RETRY_LIMIT = 3


def parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


def format_timestamp(value: datetime) -> str:
    return value.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")


class DisabledTimerService:
    def __init__(
        self,
        runtime: Any,
        systemd_adapter: Any,
        alert_notifier: Optional[Any] = None,
        logger: Optional[Any] = None,
    ) -> None:
        self.runtime = runtime
        self.systemd_adapter = systemd_adapter
        self.alert_notifier = alert_notifier
        self.logger = logger
        self.path = runtime.data_dir / DISABLED_TIMERS_FILENAME
        self.lock_path = runtime.data_dir / ".disabled_timers.lock"

    def list_records(self) -> Dict[str, Dict[str, Any]]:
        records = read_json(self.path, {})
        if isinstance(records, dict):
            return records
        return {}

    def get_record(self, timer_name: str) -> Optional[Dict[str, Any]]:
        return self.list_records().get(timer_name)

    def has_active_record(self, timer_name: str) -> bool:
        record = self.get_record(timer_name)
        return bool(record and not record.get("restore_failed"))

    def disable(
        self,
        task_name: str,
        timer_name: str,
        *,
        mode: str,
        expires_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        if mode not in {"temporary", "permanent"}:
            raise ValueError("mode must be temporary or permanent")
        if mode == "temporary" and expires_at is None:
            raise ValueError("temporary disables require expires_at")

        if not self.runtime.is_fake:
            self.systemd_adapter.disable_timer_now(timer_name)

        record = {
            "task_name": task_name,
            "timer_name": timer_name,
            "mode": mode,
            "created_at": format_timestamp(datetime.now()),
            "restore_attempts": 0,
            "restore_failed": False,
        }
        if mode == "temporary" and expires_at is not None:
            record["expires_at"] = format_timestamp(expires_at)

        def update(records: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
            if not isinstance(records, dict):
                records = {}
            records[timer_name] = record
            return records

        locked_json_update(
            self.path,
            self.lock_path,
            {},
            update,
            file_mode=0o644,
            lock_mode=0o644,
        )
        return record

    def enable(self, timer_name: str) -> None:
        if not self.runtime.is_fake:
            self.systemd_adapter.enable_timer_now(timer_name)

        def update(records: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
            if isinstance(records, dict):
                records.pop(timer_name, None)
            return records if isinstance(records, dict) else {}

        locked_json_update(
            self.path,
            self.lock_path,
            {},
            update,
            file_mode=0o644,
            lock_mode=0o644,
        )

    def restore_expired(self, *, now: Optional[datetime] = None) -> Dict[str, List[str]]:
        now = now or datetime.utcnow()
        restored = []  # type: List[str]
        failed = []  # type: List[str]

        for timer_name, record in sorted(self.list_records().items()):
            if record.get("mode") != "temporary" or record.get("restore_failed"):
                continue
            expires_at = parse_timestamp(record.get("expires_at"))
            if expires_at is None or expires_at > now:
                continue
            try:
                if not self.runtime.is_fake:
                    self.systemd_adapter.enable_timer_now(timer_name)
                self._remove_record(timer_name)
                restored.append(timer_name)
            except Exception as exc:
                failed.append(timer_name)
                self._record_restore_failure(timer_name, record, exc)

        return {"restored": restored, "failed": failed}

    def _remove_record(self, timer_name: str) -> None:
        def update(records: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
            if isinstance(records, dict):
                records.pop(timer_name, None)
            return records if isinstance(records, dict) else {}

        locked_json_update(
            self.path,
            self.lock_path,
            {},
            update,
            file_mode=0o644,
            lock_mode=0o644,
        )

    def _record_restore_failure(
        self,
        timer_name: str,
        record: Dict[str, Any],
        exc: Exception,
    ) -> None:
        next_attempts = int(record.get("restore_attempts") or 0) + 1
        restore_failed = next_attempts >= RESTORE_RETRY_LIMIT

        def update(records: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
            current = records.get(timer_name, record) if isinstance(records, dict) else record
            current["restore_attempts"] = next_attempts
            current["last_restore_error"] = str(exc)
            current["last_restore_attempt_at"] = format_timestamp(datetime.now())
            current["restore_failed"] = restore_failed
            records[timer_name] = current
            return records

        locked_json_update(
            self.path,
            self.lock_path,
            {},
            update,
            file_mode=0o644,
            lock_mode=0o644,
        )

        if restore_failed and self.alert_notifier:
            task_name = record.get("task_name") or timer_name
            message = (
                f"SimpleSaferServer could not re-enable {task_name} ({timer_name}) "
                f"after {RESTORE_RETRY_LIMIT} attempts. Use Enable Schedule from the task page "
                "after checking systemd."
            )
            self.alert_notifier.notify(
                "Schedule restore failed",
                message,
                alert_type="error",
                source="scheduled_tasks",
            )
