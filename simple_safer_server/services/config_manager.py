import configparser
import io
import logging
import os
import stat

from cryptography.fernet import Fernet

from simple_safer_server.services.alert_store import AlertStore
from simple_safer_server.services.file_persistence import (
    atomic_write_json,
    atomic_write_text,
    locked_path,
    read_json,
)
from simple_safer_server.services.runtime import get_runtime


class ConfigManager:
    def __init__(self, runtime=None):
        self.runtime = runtime or get_runtime()
        self.config_dir = self.runtime.config_dir
        self.config_path = self.config_dir / 'config.conf'
        self.secrets_path = self.config_dir / '.secrets'
        self.secrets_lock_path = self.config_dir / '.secrets.lock'
        self.key_path = self.config_dir / '.key'
        self.alerts_path = self.config_dir / 'alerts.json'
        self.alert_store = AlertStore(self.alerts_path)
        self.config = configparser.ConfigParser()
        self.logger = logging.getLogger(__name__)

        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.chmod(0o700)

        # Initialize configuration
        self.load_config()
        self._init_secrets()
        self._init_alerts()

    def _init_secrets(self):
        """Initialize the secrets management system"""
        if not self.key_path.exists():
            key = Fernet.generate_key()
            self._create_private_file(self.key_path, key)
        self._ensure_private_regular_file(self.key_path)

        if not self.secrets_path.exists():
            self._create_private_file(self.secrets_path, b'{}')
        self._ensure_private_regular_file(self.secrets_path)

        self.cipher = Fernet(self.key_path.read_bytes())

    def _create_private_file(self, path, data):
        # Key material and encrypted secret stores must be mode 0600 from the
        # first inode creation; chmod-after-write can briefly expose umask perms.
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(str(path), flags, 0o600)
        except FileExistsError:
            # Another worker created the file between exists() and os.open().
            # The explicit validation call below owns the existing-file policy.
            return
        try:
            os.write(fd, data)
        finally:
            os.close(fd)

    def _ensure_private_regular_file(self, path):
        # Treat the config directory as trusted and private, but do not accept
        # symlinks or device files for secret material.
        file_stat = path.lstat()
        if not stat.S_ISREG(file_stat.st_mode):
            raise RuntimeError(f"Refusing to use non-regular secret file: {path}")
        path.chmod(0o600)

    def _init_alerts(self):
        """Initialize the alerts storage system"""
        self.alert_store.initialize()

    def load_config(self):
        """Load the configuration file"""
        # ConfigParser.read() merges into existing state, so reloads need a
        # fresh parser or deleted options can linger in memory.
        self.config = configparser.ConfigParser()
        if self.config_path.exists():
            self.config.read(self.config_path)
        else:
            self.create_default_config()

    def create_default_config(self):
        """Create default configuration"""
        self.config['system'] = {'username': '', 'server_name': '', 'setup_complete': 'false'}

        self.config['backup'] = {
            'email_address': '',
            'from_address': '',
            'uuid': '',
            'usb_id': '',
            'mount_point': self.runtime.default_mount_point,
            'rclone_dir': '',
            'bandwidth_limit': '',
        }

        self.config['schedule'] = {'backup_cloud_time': '03:00'}

        self.config['hdsentinel'] = {'enabled': 'true', 'health_change_alert': 'true'}

        self.config['apt_updates'] = {
            'managed': 'false',
            'update_package_lists': 'false',
            'unattended_upgrade': 'false',
            'autoclean_interval': '7',
        }

        self.config['ddns'] = {
            'duckdns_enabled': 'false',
            'duckdns_domain': '',
            'cloudflare_enabled': 'false',
            'cloudflare_zone': '',
            'cloudflare_record': '',
            'cloudflare_proxy': 'false',
        }

        self.save_config()

    def save_config(self):
        """Save the configuration to file"""
        stream = io.StringIO()
        self.config.write(stream)
        atomic_write_text(self.config_path, stream.getvalue(), mode=0o644)

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
            # Multiple admin requests can update different credentials at once;
            # lock the whole read/modify/replace sequence so one request cannot
            # overwrite another request's freshly stored key.
            with locked_path(self.secrets_lock_path, mode=0o600):
                secrets = read_json(self.secrets_path, {})
                encrypted = self.cipher.encrypt(value.encode())
                secrets[key] = encrypted.decode()
                atomic_write_json(self.secrets_path, secrets, mode=0o600)
        except Exception as e:
            self.logger.error(f"Error storing secret: {e}")
            raise

    def get_secret(self, key, default=None):
        """Retrieve a sensitive value"""
        try:
            secrets = read_json(self.secrets_path, {})
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
            self.alert_store.append_alert(title, message, alert_type=alert_type, source=source)
            self.logger.info(f"Alert logged: {title}")
            return True
        except Exception as e:
            self.logger.error(f"Error logging alert: {e}")
            return False

    def get_alerts(self, limit=None, unread_only=False):
        """Get alerts from the alerts file"""
        try:
            return self.alert_store.list_alerts(limit=limit, unread_only=unread_only)
        except Exception as e:
            self.logger.error(f"Error reading alerts: {e}")
            return []

    def mark_alert_read(self, alert_id):
        """Mark an alert as read"""
        try:
            self.alert_store.mark_alert_read(alert_id)
            return True
        except Exception as e:
            self.logger.error(f"Error marking alert as read: {e}")
            return False

    def clear_alerts(self):
        """Clear all alerts"""
        try:
            self.alert_store.clear()
            self.logger.info("All alerts cleared")
            return True
        except Exception as e:
            self.logger.error(f"Error clearing alerts: {e}")
            return False

    def mark_all_alerts_read(self):
        """Mark all alerts as read"""
        try:
            self.alert_store.mark_all_read()
            return True
        except Exception as e:
            self.logger.error(f"Error marking all alerts as read: {e}")
            return False

    def is_setup_complete(self):
        """Check if initial setup is complete; always reload config to ensure freshness"""
        self.load_config()
        return str(self.get_value('system', 'setup_complete', 'false')).lower() == 'true'

    def mark_setup_complete(self):
        """Mark the initial setup as complete"""
        self.set_value('system', 'setup_complete', 'true')

    def get_all_config(self):
        """Get all non-sensitive configuration"""
        config_dict = {}
        for section in self.config.sections():
            config_dict[section] = dict(self.config[section])
        return config_dict
