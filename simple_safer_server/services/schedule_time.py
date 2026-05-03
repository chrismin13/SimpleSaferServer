import re

STRICT_UI_TIME_RE = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")


class ScheduleTimeError(ValueError):
    """Raised when a backup schedule time cannot be normalized."""


def normalize_ui_schedule_time(value):
    """Return a two-digit HH:MM backup time accepted by browser-facing APIs."""
    text = str(value or "").strip()
    if not STRICT_UI_TIME_RE.match(text):
        raise ScheduleTimeError("Time must be in HH:MM format (24-hour).")
    return text


def normalize_legacy_schedule_time(value):
    """Return HH:MM while accepting older config shapes used before UI validation was strict."""
    text = str(value or "").strip()
    parts = text.split(":")
    if len(parts) not in (2, 3):
        raise ScheduleTimeError("schedule.backup_cloud_time must be in HH:MM or HH:MM:SS format")
    # int() accepts signs and surrounding whitespace; timer config should only
    # accept plain decimal components from persisted config.
    if not all(part.isdigit() for part in parts):
        raise ScheduleTimeError("schedule.backup_cloud_time must be in HH:MM or HH:MM:SS format")

    hour = int(parts[0])
    minute = int(parts[1])
    second = int(parts[2]) if len(parts) == 3 else 0
    if not (0 <= hour < 24 and 0 <= minute < 60 and 0 <= second < 60):
        raise ScheduleTimeError("schedule.backup_cloud_time contains an invalid time")
    return f"{hour:02d}:{minute:02d}"


def systemd_schedule_time(value):
    """Return normalized hour, minute, and HH:MM:SS for systemd OnCalendar use."""
    normalized = normalize_legacy_schedule_time(value)
    hour_text, minute_text = normalized.split(":")
    hour = int(hour_text)
    minute = int(minute_text)
    return hour, minute, f"{normalized}:00"
