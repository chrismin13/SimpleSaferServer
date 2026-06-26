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


def systemd_schedule_time(value):
    """Return normalized hour, minute, and HH:MM:SS for systemd OnCalendar use."""
    normalized = normalize_ui_schedule_time(value)
    hour_text, minute_text = normalized.split(":")
    hour = int(hour_text)
    minute = int(minute_text)
    return hour, minute, f"{normalized}:00"
