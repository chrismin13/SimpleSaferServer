from datetime import date, datetime
from typing import Any, Dict, Optional

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
DEFAULT_AUTOCLEAN_INTERVAL_DAYS = 7


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


def get_support_info(
    distro_id: str, version_id: str, today: Optional[date] = None
) -> Dict[str, Any]:
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
