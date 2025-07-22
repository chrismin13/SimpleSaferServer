#!/usr/bin/env python3
"""
Standalone alert logging script for use by bash scripts.
This script can be called independently of the web UI to log alerts.
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

def log_alert(title, message, alert_type="info", source="script"):
    """Log an alert to the alerts file"""
    try:
        config_dir = Path('/etc/SimpleSaferServer')
        alerts_path = config_dir / 'alerts.json'
        
        # Ensure config directory exists
        config_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize alerts file if it doesn't exist
        if not alerts_path.exists():
            alerts_path.write_text('[]')
            alerts_path.chmod(0o644)
        
        # Read existing alerts
        alerts = json.loads(alerts_path.read_text())
        
        # Create new alert
        alert = {
            'id': len(alerts) + 1,
            'title': title,
            'message': message,
            'type': alert_type,
            'source': source,
            'timestamp': datetime.now().isoformat(),
            'read': False
        }
        alerts.append(alert)
        
        # Keep only the last 1000 alerts to prevent file from growing too large
        if len(alerts) > 1000:
            alerts = alerts[-1000:]
        
        # Write alerts back to file
        alerts_path.write_text(json.dumps(alerts, indent=2))
        print(f"Alert logged: {title}")
        return True
        
    except Exception as e:
        print(f"Error logging alert: {e}", file=sys.stderr)
        return False

def main():
    """Main function for command line usage"""
    if len(sys.argv) < 3:
        print("Usage: python3 log_alert.py <title> <message> [alert_type] [source]")
        print("Example: python3 log_alert.py 'Backup Failed' 'Cloud backup failed due to network error' 'error' 'backup_cloud'")
        sys.exit(1)
    
    title = sys.argv[1]
    message = sys.argv[2]
    alert_type = sys.argv[3] if len(sys.argv) > 3 else "info"
    source = sys.argv[4] if len(sys.argv) > 4 else "script"
    
    success = log_alert(title, message, alert_type, source)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 