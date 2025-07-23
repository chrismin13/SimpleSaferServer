import configparser
import os
from pathlib import Path
from cryptography.fernet import Fernet
import json
import logging
from datetime import datetime

class ConfigManager:
    def __init__(self):
        self.config_dir = Path('/etc/SimpleSaferServer')
        self.config_path = self.config_dir / 'config.conf'
        self.secrets_path = self.config_dir / '.secrets'
        self.key_path = self.config_dir / '.key'
        self.alerts_path = self.config_dir / 'alerts.json'
        self.config = configparser.ConfigParser()
        self.logger = logging.getLogger(__name__)
        
        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize configuration
        self.load_config()
        self._init_secrets()
        self._init_alerts()

    def _init_secrets(self):
        """Initialize the secrets management system"""
        if not self.key_path.exists():
            key = Fernet.generate_key()
            self.key_path.write_bytes(key)
            # Set proper permissions
            self.key_path.chmod(0o600)
        
        if not self.secrets_path.exists():
            self.secrets_path.write_text('{}')
            self.secrets_path.chmod(0o600)
        
        self.cipher = Fernet(self.key_path.read_bytes())

    def _init_alerts(self):
        """Initialize the alerts storage system"""
        if not self.alerts_path.exists():
            self.alerts_path.write_text('[]')
            self.alerts_path.chmod(0o644)

    def load_config(self):
        """Load the configuration file"""
        if self.config_path.exists():
            self.config.read(self.config_path)
        else:
            self.create_default_config()

    def create_default_config(self):
        """Create default configuration"""
        self.config['system'] = {
            'username': '',
            'server_name': '',
            'setup_complete': 'false'
        }
        
        self.config['backup'] = {
            'email_address': '',
            'from_address': '',
            'uuid': '',
            'usb_id': '',
            'mount_point': '/media/backup',
            'rclone_dir': '',
            'bandwidth_limit': ''
        }
        
        self.config['schedule'] = {
            'backup_cloud_time': '3:00'
        }
        
        self.save_config()

    def save_config(self):
        """Save the configuration to file"""
        with open(self.config_path, 'w') as f:
            self.config.write(f)
        # Set proper permissions
        self.config_path.chmod(0o644)

    def get_value(self, section, key, default=None):
        """Get a configuration value"""
        try:
            return self.config.get(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return default

    def set_value(self, section, key, value):
        """Set a configuration value"""
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, str(value))
        self.save_config()

    def store_secret(self, key, value):
        """Store a sensitive value"""
        try:
            secrets = json.loads(self.secrets_path.read_text())
            encrypted = self.cipher.encrypt(value.encode())
            secrets[key] = encrypted.decode()
            self.secrets_path.write_text(json.dumps(secrets))
        except Exception as e:
            self.logger.error(f"Error storing secret: {e}")
            raise

    def get_secret(self, key, default=None):
        """Retrieve a sensitive value"""
        try:
            secrets = json.loads(self.secrets_path.read_text())
            if key not in secrets:
                return default
            encrypted = secrets[key].encode()
            return self.cipher.decrypt(encrypted).decode()
        except Exception as e:
            self.logger.error(f"Error retrieving secret: {e}")
            return default

    def log_alert(self, title, message, alert_type="info", source="system"):
        """Log an alert to the alerts file"""
        try:
            alerts = self.get_alerts()
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
            
            self.alerts_path.write_text(json.dumps(alerts, indent=2))
            self.logger.info(f"Alert logged: {title}")
            return True
        except Exception as e:
            self.logger.error(f"Error logging alert: {e}")
            return False

    def get_alerts(self, limit=None, unread_only=False):
        """Get alerts from the alerts file"""
        try:
            if not self.alerts_path.exists():
                return []
            
            alerts = json.loads(self.alerts_path.read_text())
            
            if unread_only:
                alerts = [alert for alert in alerts if not alert.get('read', False)]
            
            if limit:
                alerts = alerts[-limit:]
            
            return alerts
        except Exception as e:
            self.logger.error(f"Error reading alerts: {e}")
            return []

    def mark_alert_read(self, alert_id):
        """Mark an alert as read"""
        try:
            alerts = self.get_alerts()
            for alert in alerts:
                if alert['id'] == alert_id:
                    alert['read'] = True
                    break
            
            self.alerts_path.write_text(json.dumps(alerts, indent=2))
            return True
        except Exception as e:
            self.logger.error(f"Error marking alert as read: {e}")
            return False

    def clear_alerts(self):
        """Clear all alerts"""
        try:
            self.alerts_path.write_text('[]')
            self.logger.info("All alerts cleared")
            return True
        except Exception as e:
            self.logger.error(f"Error clearing alerts: {e}")
            return False

    def mark_all_alerts_read(self):
        """Mark all alerts as read"""
        try:
            alerts = self.get_alerts()
            for alert in alerts:
                alert['read'] = True
            self.alerts_path.write_text(json.dumps(alerts, indent=2))
            return True
        except Exception as e:
            self.logger.error(f"Error marking all alerts as read: {e}")
            return False

    def is_setup_complete(self):
        """Check if initial setup is complete; always reload config to ensure freshness"""
        self.load_config()
        return self.get_value('system', 'setup_complete', 'false').lower() == 'true'

    def mark_setup_complete(self):
        """Mark the initial setup as complete"""
        self.set_value('system', 'setup_complete', 'true')

    def get_all_config(self):
        """Get all non-sensitive configuration"""
        config_dict = {}
        for section in self.config.sections():
            config_dict[section] = dict(self.config[section])
        return config_dict

    def validate_config(self):
        """Validate the current configuration"""
        required_fields = {
            'system': ['username', 'server_name'],
            'backup': ['email_address', 'uuid', 'usb_id', 'mount_point', 'rclone_dir']
        }
        
        missing_fields = []
        for section, fields in required_fields.items():
            for field in fields:
                if not self.get_value(section, field):
                    missing_fields.append(f"{section}.{field}")
        
        return len(missing_fields) == 0, missing_fields 