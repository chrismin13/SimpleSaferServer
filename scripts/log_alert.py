#!/usr/bin/env python3
"""
Standalone alert logging script for use by bash scripts.
This script can be called independently of the web UI to log alerts.
"""

import os
import sys
from pathlib import Path


def _add_app_to_path():
    script_path = Path(__file__).resolve()
    candidates = [
        script_path.parents[1],
        Path('/opt/SimpleSaferServer'),
    ]
    for candidate in candidates:
        if (candidate / 'simple_safer_server').exists():
            sys.path.insert(0, str(candidate))
            return


_add_app_to_path()

from simple_safer_server.services.alert_store import AlertStore  # noqa: E402


def log_alert(title, message, alert_type="info", source="script"):
    """Log an alert to the alerts file"""
    try:
        config_dir = Path(os.environ.get('SSS_CONFIG_DIR', '/etc/SimpleSaferServer'))
        alerts_path = config_dir / 'alerts.json'

        config_dir.mkdir(parents=True, exist_ok=True)
        # This directory also holds encrypted secrets, so the alert script must
        # preserve ConfigManager's private-directory policy when it runs first.
        config_dir.chmod(0o700)
        store = AlertStore(alerts_path)
        store.initialize()
        store.append_alert(title, message, alert_type=alert_type, source=source)

        print(f"Alert logged: {title}")
        return True

    except Exception as e:
        print(f"Error logging alert: {e}", file=sys.stderr)
        return False


def main():
    """Main function for command line usage"""
    if len(sys.argv) < 3:
        print("Usage: python3 log_alert.py <title> <message> [alert_type] [source]")
        print(
            "Example: python3 log_alert.py 'Backup Failed' 'Cloud backup failed due to network error' 'error' 'backup_cloud'"
        )
        sys.exit(1)

    title = sys.argv[1]
    message = sys.argv[2]
    alert_type = sys.argv[3] if len(sys.argv) > 3 else "info"
    source = sys.argv[4] if len(sys.argv) > 4 else "script"

    success = log_alert(title, message, alert_type, source)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
