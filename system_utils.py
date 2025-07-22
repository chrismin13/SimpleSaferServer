import subprocess
import json
import logging
from pathlib import Path
import os
import re
import shutil

class SystemUtils:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def run_command(self, command, check=True):
        """Run a system command and return the result"""
        try:
            result = subprocess.run(
                command,
                check=check,
                capture_output=True,
                text=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Command failed: {e.stderr}")
            raise

    def setup_rclone(self, config):
        """Set up rclone configuration"""
        try:
            # Create rclone config directory if it doesn't exist
            rclone_dir = Path.home() / '.config' / 'rclone'
            rclone_dir.mkdir(parents=True, exist_ok=True)
            
            # Write rclone config
            config_path = rclone_dir / 'rclone.conf'
            config_path.write_text(config)
            config_path.chmod(0o600)
            
            return True
        except Exception as e:
            self.logger.error(f"Error setting up rclone: {e}")
            return False

    def setup_systemd_service(self, service_name, command, user, timer=None):
        """Set up systemd service and timer"""
        try:
            # Create service file
            service_content = f"""[Unit]
Description={service_name} service
After=network.target

[Service]
Type=simple
User={user}
ExecStart={command}
Restart=on-failure

[Install]
WantedBy=multi-user.target
"""
            
            service_path = Path(f'/etc/systemd/system/{service_name}.service')
            service_path.write_text(service_content)
            
            # Create timer if specified
            if timer:
                timer_content = f"""[Unit]
Description=Run {service_name} on schedule

[Timer]
OnCalendar={timer}
Persistent=true

[Install]
WantedBy=timers.target
"""
                timer_path = Path(f'/etc/systemd/system/{service_name}.timer')
                timer_path.write_text(timer_content)
            
            # Reload systemd and enable service
            self.run_command(['systemctl', 'daemon-reload'])
            self.run_command(['systemctl', 'enable', f'{service_name}.service'])
            if timer:
                self.run_command(['systemctl', 'enable', f'{service_name}.timer'])
                self.run_command(['systemctl', 'start', f'{service_name}.timer'])
            
            return True
        except Exception as e:
            self.logger.error(f"Error setting up systemd service: {e}")
            return False

    def write_msmtp_config(self, email, server, port, user, password):
        """Write /etc/msmtprc with the supplied SMTP settings"""
        try:
            content = f"""defaults
port {port}
tls on
tls_trust_file /etc/ssl/certs/ca-certificates.crt

account simplesaferserver
host {server}
from {email}
auth on
user {user}
password {password}

account default : simplesaferserver
"""
            path = Path('/etc/msmtprc')
            path.write_text(content)
            path.chmod(0o600)
            return True
        except Exception as e:
            self.logger.error(f"Error writing msmtp config: {e}")
            return False 

    def get_parent_device(self, partition_path):
        """Given a partition device path (e.g. /dev/sda1), return the parent drive (e.g. /dev/sda)."""
        try:
            # Use lsblk to get the parent device
            result = self.run_command(['lsblk', '-no', 'PKNAME', partition_path])
            if result:
                parent = result.strip()
                return f"/dev/{parent}"
            # Fallback: strip trailing digits (works for /dev/sda1, /dev/nvme0n1p1, etc.)
            import re
            m = re.match(r"(/dev/[a-zA-Z0-9]+)", partition_path)
            if m:
                return m.group(1)
            return None
        except Exception as e:
            self.logger.error(f"Error getting parent device for {partition_path}: {e}")
            return None 

    def is_mounted(self, mount_point):
        """Check if the given mount point is currently mounted."""
        try:
            with open('/proc/mounts', 'r') as f:
                for line in f:
                    if mount_point in line.split():
                        return True
            return False
        except Exception as e:
            self.logger.error(f"Error checking mount status for {mount_point}: {e}")
            return False

    def install_systemd_scripts(self, config):
        """Install systemd scripts from the local scripts directory to /usr/local/bin/"""
        try:
            # Get the current script directory (relative to the project root)
            current_dir = Path(__file__).parent
            scripts_source_dir = current_dir / 'scripts'
            scripts_dest_dir = Path('/usr/local/bin')
            
            if not scripts_source_dir.exists():
                self.logger.error(f"Scripts source directory not found: {scripts_source_dir}")
                return False, "Scripts source directory not found"
            
            # Create destination directory if it doesn't exist
            scripts_dest_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy and configure each script
            script_files = ['check_mount.sh', 'check_health.sh', 'backup_cloud.sh', 'predict_health.py', 'log_alert.py']
            
            for script_file in script_files:
                source_path = scripts_source_dir / script_file
                dest_path = scripts_dest_dir / script_file
                
                if not source_path.exists():
                    self.logger.warning(f"Script file not found: {source_path}")
                    continue
                
                # Read the script content
                script_content = source_path.read_text()
                
                # Replace configuration variables in the script
                script_content = self._configure_script(script_content, config)
                
                # Write the configured script
                dest_path.write_text(script_content)
                dest_path.chmod(0o755)  # Make executable
                
                self.logger.info(f"Installed script: {dest_path}")
            
            return True, None
            
        except Exception as e:
            self.logger.error(f"Error installing systemd scripts: {e}")
            return False, str(e)

    def _configure_script(self, script_content, config):
        """Configure script content with the current configuration"""
        try:
            # Extract configuration values
            backup_config = config.get('backup', {})
            system_config = config.get('system', {})
            
            mount_point = backup_config.get('mount_point', '/media/backup')
            uuid = backup_config.get('uuid', '')
            usb_id = backup_config.get('usb_id', '')
            email_address = backup_config.get('email_address', '')
            rclone_dir = backup_config.get('rclone_dir', '')
            bandwidth_limit = backup_config.get('bandwidth_limit', '')
            server_name = system_config.get('server_name', 'SimpleSaferServer')
            
            # Replace variables in the script
            replacements = {
                'MOUNT_POINT': mount_point,
                'UUID': uuid,
                'USB_ID': usb_id,
                'EMAIL_ADDRESS': email_address,
                'RCLONE_DIR': rclone_dir,
                'BANDWIDTH_LIMIT': bandwidth_limit,
                'SERVER_NAME': server_name
            }
            
            for var_name, value in replacements.items():
                script_content = script_content.replace(f'${var_name}', str(value))
            
            return script_content
            
        except Exception as e:
            self.logger.error(f"Error configuring script: {e}")
            return script_content

    def create_systemd_config_file(self, config):
        """Create the /etc/SimpleSaferServer/config.conf file for scripts and Python (INI format)"""
        try:
            backup_config = config.get('backup', {})
            system_config = config.get('system', {})
            schedule_config = config.get('schedule', {})

            config_content = f"""[system]
username = {system_config.get('username', '')}
server_name = {system_config.get('server_name', 'SimpleSaferServer')}
setup_complete = {system_config.get('setup_complete', 'false')}

[backup]
mount_point = {backup_config.get('mount_point', '/media/backup')}
uuid = {backup_config.get('uuid', '')}
usb_id = {backup_config.get('usb_id', '')}
email_address = {backup_config.get('email_address', '')}
rclone_dir = {backup_config.get('rclone_dir', '')}
bandwidth_limit = {backup_config.get('bandwidth_limit', '')}
cloud_mode = {backup_config.get('cloud_mode', '')}
mega_email = {backup_config.get('mega_email', '')}
mega_pass = {backup_config.get('mega_pass', '')}
mega_folder = {backup_config.get('mega_folder', '')}

[schedule]
backup_cloud_time = {schedule_config.get('backup_cloud_time', '')}
"""
            # Create the config directory
            config_dir = Path('/etc/SimpleSaferServer')
            config_dir.mkdir(parents=True, exist_ok=True)
            # Write the config file
            config_path = config_dir / 'config.conf'
            config_path.write_text(config_content)
            config_path.chmod(0o644)
            self.logger.info(f"Created systemd config file: {config_path}")
            return True, None
        except Exception as e:
            self.logger.error(f"Error creating systemd config file: {e}")
            return False, str(e)

    def install_systemd_services_and_timers(self, config):
        """Install systemd services and timers with proper formatting"""
        try:
            schedule = config.get('schedule', {})
            backup_cloud_time = schedule.get('backup_cloud_time', '3:00:00')
            
            # Parse the backup time and calculate sequential times
            backup_hour, backup_minute = map(int, backup_cloud_time.split(':'))
            
            # Calculate check_health time (1 minute before backup)
            check_health_minute = backup_minute - 1
            check_health_hour = backup_hour
            if check_health_minute < 0:
                check_health_minute += 60
                check_health_hour = (check_health_hour - 1) % 24
            check_health_time = f"{check_health_hour:02d}:{check_health_minute:02d}:00"
            
            # Calculate check_mount time (2 minutes before backup)
            check_mount_minute = backup_minute - 2
            check_mount_hour = backup_hour
            if check_mount_minute < 0:
                check_mount_minute += 60
                check_mount_hour = (check_mount_hour - 1) % 24
            check_mount_time = f"{check_mount_hour:02d}:{check_mount_minute:02d}:00"
            
            # Define services and timers with proper formatting
            services = {
                'check_mount.service': f"""[Unit]
Description=Check USB Mount Status
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/check_mount.sh
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
""",
                'check_health.service': f"""[Unit]
Description=Drive Health Check using XGBoost Model
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/check_health.sh
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
""",
                'backup_cloud.service': f"""[Unit]
Description=Cloud Backup Service
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/backup_cloud.sh
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
""",
                'check_mount.timer': f"""[Unit]
Description=Run mount check at scheduled time

[Timer]
OnCalendar=*-*-* {check_mount_time}
Persistent=true
RandomizedDelaySec=30

[Install]
WantedBy=timers.target
""",
                'check_health.timer': f"""[Unit]
Description=Run health check at scheduled time

[Timer]
OnCalendar=*-*-* {check_health_time}
Persistent=true
RandomizedDelaySec=30

[Install]
WantedBy=timers.target
""",
                'backup_cloud.timer': f"""[Unit]
Description=Run cloud backup at scheduled time

[Timer]
OnCalendar=*-*-* {backup_cloud_time}
Persistent=true
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
"""
            }
            
            # Write all service and timer files
            for filename, content in services.items():
                file_path = Path(f'/etc/systemd/system/{filename}')
                file_path.write_text(content)
                self.logger.info(f"Created systemd file: {file_path}")
            
            # Reload systemd daemon
            self.run_command(['systemctl', 'daemon-reload'])
            
            # Enable and start services and timers
            for service_name in ['check_mount', 'check_health', 'backup_cloud']:
                # Enable services
                self.run_command(['systemctl', 'enable', f'{service_name}.service'])
                # Enable timers
                self.run_command(['systemctl', 'enable', f'{service_name}.timer'])
                # Start timers (services will be started by timers)
                self.run_command(['systemctl', 'start', f'{service_name}.timer'])
                
                self.logger.info(f"Enabled and started {service_name} service and timer")
            
            return True, None
            
        except Exception as e:
            self.logger.error(f"Error installing systemd services and timers: {e}")
            return False, str(e) 