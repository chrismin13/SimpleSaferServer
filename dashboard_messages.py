import re
from datetime import datetime
from typing import Optional


_IGNORED_TIME_VALUES = {
    '',
    '-',
    'never',
    'unknown',
    'not run yet',
    'not scheduled',
    'retrieval error',
}


def parse_server_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse the mixed timestamp formats the dashboard already shows for task times."""
    trimmed = (value or '').strip()
    if not trimmed or trimmed.lower() in _IGNORED_TIME_VALUES:
        return None

    try:
        return datetime.fromisoformat(trimmed)
    except ValueError:
        pass

    # systemd-style values often include a weekday prefix and timezone suffix
    # that datetime.fromisoformat does not accept directly.
    normalized = re.sub(r'^[A-Za-z]{3}\s+', '', trimmed)
    normalized = re.sub(r'\s+[A-Z]{2,5}$', '', normalized)

    try:
        return datetime.fromisoformat(normalized.replace(' ', 'T'))
    except ValueError:
        pass

    match = re.match(r'^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$', normalized)
    if not match:
        return None

    year, month, day, hour, minute, second = (int(part) for part in match.groups())
    return datetime(year, month, day, hour, minute, second)


def format_future_delay(value: Optional[str], now: Optional[datetime] = None) -> Optional[str]:
    """Return a short human-readable countdown such as 'in about 2h 13m'."""
    target_time = parse_server_datetime(value)
    if not target_time:
        return None

    now = now or datetime.now()
    diff_seconds = int((target_time - now).total_seconds())
    if diff_seconds <= 0:
        return None

    if diff_seconds < 60:
        return 'in about a few seconds'

    remaining_minutes = diff_seconds // 60
    units = [
        ('w', 10080),
        ('d', 1440),
        ('h', 60),
        ('m', 1),
    ]

    parts = []
    for suffix, size in units:
        if len(parts) >= 3:
            break
        amount = remaining_minutes // size
        if amount > 0:
            parts.append(f'{amount}{suffix}')
            remaining_minutes -= amount * size

    if not parts:
        parts.append('0m')

    return 'in about {}'.format(' '.join(parts))


def build_dashboard_unmount_success_message(
    base_message: str,
    next_check_mount_run: Optional[str],
    *,
    availability_phrase: str = 'stays connected',
    remount_verb: str = 'remount',
) -> str:
    """Describe that dashboard unmount is temporary because the drive stays managed."""
    delay = format_future_delay(next_check_mount_run)
    if delay:
        return (
            f'{base_message} If it {availability_phrase}, SimpleSaferServer may '
            f'{remount_verb} it automatically during the next Check Mount run, {delay}.'
        )

    return (
        f'{base_message} If it {availability_phrase}, SimpleSaferServer may '
        f'{remount_verb} it automatically during the next scheduled Check Mount run.'
    )
