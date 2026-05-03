import configparser
import io
import logging
import re
import shutil

from simple_safer_server.adapters.command_runner import CalledProcessError, CommandRunner
from simple_safer_server.services.runtime import get_fake_state, get_runtime


def _time_before(hour, minute, *, minutes_before):
    total_minutes = ((hour * 60) + minute - minutes_before) % (24 * 60)
    return divmod(total_minutes, 60)


def _parse_backup_cloud_time(backup_cloud_time):
    """Return normalized backup time fields for systemd OnCalendar entries."""
    time_parts = backup_cloud_time.split(':')
    if len(time_parts) not in (2, 3):
        raise ValueError("schedule.backup_cloud_time must be in HH:MM or HH:MM:SS format")
    # int() accepts signs and surrounding whitespace; systemd timer config should only use digits.
    if not all(time_part.isdigit() for time_part in time_parts):
        raise ValueError("schedule.backup_cloud_time must be in HH:MM or HH:MM:SS format")
    backup_hour = int(time_parts[0])
    backup_minute = int(time_parts[1])
    backup_second = int(time_parts[2]) if len(time_parts) == 3 else 0
    if not (0 <= backup_hour < 24 and 0 <= backup_minute < 60 and 0 <= backup_second < 60):
        raise ValueError("schedule.backup_cloud_time contains an invalid time")
    return backup_hour, backup_minute, f"{backup_hour:02d}:{backup_minute:02d}:{backup_second:02d}"


class SystemUtils:
    def __init__(self, runtime=None, command_runner=None):
        self.runtime = runtime or get_runtime()
        self.command_runner = command_runner or CommandRunner()
        self.fake_state = get_fake_state() if self.runtime.is_fake else None
        self.logger = logging.getLogger(__name__)

    def run_command(self, command, check=True):
        """Run a system command and return the result"""
        try:
            result = self.command_runner.run(command, check=check, capture_output=True, text=True)
            return result.stdout.strip()
        except CalledProcessError as e:
            self.logger.error(f"Command failed: {e.stderr}")
            raise

    def setup_rclone(self, config):
        """Set up rclone configuration"""
        try:
            # Create rclone config directory if it doesn't exist
            rclone_dir = self.runtime.rclone_config_dir
            rclone_dir.mkdir(parents=True, exist_ok=True)

            # Write rclone config
            config_path = rclone_dir / 'rclone.conf'
            config_path.write_text(config)
            config_path.chmod(0o600)

            return True
        except Exception as e:
            self.logger.error(f"Error setting up rclone: {e}")
            return False

    def write_msmtp_config(self, from_address, server, port, user, password):
        """Write /etc/msmtprc with the supplied SMTP settings. 'from_address' is used for the 'from' line and as the envelope-from in scripts."""
        try:
            content = f"""defaults
port {port}
tls on
tls_trust_file /etc/ssl/certs/ca-certificates.crt

account simplesaferserver
host {server}
from {from_address}
auth on
user {user}
password {password}

account default : simplesaferserver
"""
            path = self.runtime.msmtp_config_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            path.chmod(0o600)
            return True
        except Exception as e:
            self.logger.error(f"Error writing msmtp config: {e}")
            return False

    def get_parent_device(self, partition_path):
        """Given a partition device path (e.g. /dev/sda1), return the parent drive (e.g. /dev/sda)."""
        if self.runtime.is_fake and partition_path.startswith('/dev/fakebackup'):
            return '/dev/fakebackup'
        try:
            # Use lsblk to get the parent device
            result = self.run_command(['lsblk', '-no', 'PKNAME', partition_path])
            if result:
                parent = result.strip()
                return f"/dev/{parent}"
            # Fallback for environments where lsblk cannot report PKNAME. NVMe
            # and MMC partition names use a "p" separator; SATA-style names do not.
            m = re.match(r"^(/dev/(?:nvme\d+n\d+|mmcblk\d+|loop\d+))p\d+$", partition_path)
            if m:
                return m.group(1)
            m = re.match(r"^(/dev/[a-z]+)\d+$", partition_path)
            if m:
                return m.group(1)
            return None
        except Exception as e:
            self.logger.error(f"Error getting parent device for {partition_path}: {e}")
            return None

    def is_mounted(self, mount_point):
        """Check if the given mount point is currently mounted."""
        if self.runtime.is_fake:
            if self.fake_state is None:
                raise RuntimeError("Fake runtime is missing fake state.")
            return self.fake_state.is_mounted(mount_point)
        try:
            with open('/proc/mounts') as f:
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
            scripts_source_dir = self.runtime.repo_root / 'scripts'
            scripts_dest_dir = self.runtime.bin_dir

            if not scripts_source_dir.exists():
                self.logger.error(f"Scripts source directory not found: {scripts_source_dir}")
                return False, "Scripts source directory not found"

            # Create destination directory if it doesn't exist
            scripts_dest_dir.mkdir(parents=True, exist_ok=True)

            # Copy each script as-is. The scripts read live values from
            # /etc/SimpleSaferServer/config.conf, so templating them here can
            # accidentally bake stale UUID/USB_ID values into the installed copy.
            script_files = [
                'check_mount.sh',
                'check_health.sh',
                'check_health.py',
                'backup_cloud.sh',
                'log_alert.py',
                'ddns_update.sh',
                'ddns_update.py',
            ]

            for script_file in script_files:
                source_path = scripts_source_dir / script_file
                dest_path = scripts_dest_dir / script_file

                if not source_path.exists():
                    self.logger.warning(f"Script file not found: {source_path}")
                    continue

                shutil.copy2(source_path, dest_path)
                dest_path.chmod(0o755)  # Make executable

                self.logger.info(f"Installed script: {dest_path}")

            return True, None

        except Exception as e:
            self.logger.error(f"Error installing systemd scripts: {e}")
            return False, str(e)

    def create_systemd_config_file(self, config):
        """Create the /etc/SimpleSaferServer/config.conf file for scripts and Python (INI format)"""
        try:
            backup_config = config.get('backup', {})
            system_config = config.get('system', {})
            schedule_config = config.get('schedule', {})
            hdsentinel_config = config.get('hdsentinel', {})
            ddns_config = config.get('ddns', {})
            parser = configparser.ConfigParser()
            # This file is consumed by both Python helpers and shell scripts.
            # Let ConfigParser serialize values so first-run setup input cannot
            # create accidental extra sections or keys by containing newlines.
            parser['system'] = {
                'username': str(system_config.get('username', '')),
                'server_name': str(system_config.get('server_name', 'SimpleSaferServer')),
                'setup_complete': str(system_config.get('setup_complete', 'false')),
            }
            parser['backup'] = {
                'mount_point': str(
                    backup_config.get('mount_point', self.runtime.default_mount_point)
                ),
                'uuid': str(backup_config.get('uuid', '')),
                'usb_id': str(backup_config.get('usb_id', '')),
                'email_address': str(backup_config.get('email_address', '')),
                'from_address': str(backup_config.get('from_address', '')),
                'rclone_dir': str(backup_config.get('rclone_dir', '')),
                'bandwidth_limit': str(backup_config.get('bandwidth_limit', '')),
                'cloud_mode': str(backup_config.get('cloud_mode', '')),
                'mega_email': str(backup_config.get('mega_email', '')),
                'mega_pass': str(backup_config.get('mega_pass', '')),
                'mega_folder': str(backup_config.get('mega_folder', '')),
            }
            parser['schedule'] = {
                'backup_cloud_time': str(schedule_config.get('backup_cloud_time', '')),
            }
            parser['hdsentinel'] = {
                'enabled': str(hdsentinel_config.get('enabled', 'true')),
                'health_change_alert': str(hdsentinel_config.get('health_change_alert', 'true')),
            }
            parser['ddns'] = {
                'duckdns_enabled': str(ddns_config.get('duckdns_enabled', 'false')),
                'duckdns_domain': str(ddns_config.get('duckdns_domain', '')),
                'cloudflare_enabled': str(ddns_config.get('cloudflare_enabled', 'false')),
                'cloudflare_zone': str(ddns_config.get('cloudflare_zone', '')),
                'cloudflare_record': str(ddns_config.get('cloudflare_record', '')),
                'cloudflare_proxy': str(ddns_config.get('cloudflare_proxy', 'false')),
            }
            config_stream = io.StringIO()
            parser.write(config_stream)
            config_content = config_stream.getvalue()
            # Create the config directory
            config_dir = self.runtime.config_dir
            config_dir.mkdir(parents=True, exist_ok=True)
            # Write the config file
            config_path = config_dir / 'config.conf'
            config_path.write_text(config_content)
            # This file contains backup/DDNS credentials and is read by root-owned services.
            config_path.chmod(0o600)
            self.logger.info(f"Created systemd config file: {config_path}")
            return True, None
        except Exception as e:
            self.logger.error(f"Error creating systemd config file: {e}")
            return False, str(e)

    def install_systemd_services_and_timers(self, config, activate_timers=True):
        """Install systemd services/timers and optionally activate the recurring work."""
        try:
            schedule = config.get('schedule', {})
            backup_cloud_time = schedule.get('backup_cloud_time', '3:00:00')

            # Parse the backup time and calculate sequential times.
            backup_hour, backup_minute, backup_cloud_time = _parse_backup_cloud_time(
                backup_cloud_time
            )

            # Keep the pre-backup jobs spaced out so randomized timer delay or
            # slow USB spin-up is less likely to make health start before mount.
            check_health_hour, check_health_minute = _time_before(
                backup_hour,
                backup_minute,
                minutes_before=2,
            )
            check_health_time = f"{check_health_hour:02d}:{check_health_minute:02d}:00"

            check_mount_hour, check_mount_minute = _time_before(
                backup_hour,
                backup_minute,
                minutes_before=4,
            )
            check_mount_time = f"{check_mount_hour:02d}:{check_mount_minute:02d}:00"

            # Define services and timers with proper formatting
            services = {
                'check_mount.service': """[Unit]
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
                'check_health.service': """[Unit]
Description=Drive Health Check
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
                'backup_cloud.service': """[Unit]
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
""",
                'ddns_update.service': """[Unit]
Description=DDNS Update Service
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/ddns_update.sh
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
""",
                'ddns_update.timer': """[Unit]
Description=Run DDNS update every 5 minutes

[Timer]
OnCalendar=*:0/5
# Spread requests so all installs don't hit provider APIs on the exact same boundary
RandomizedDelaySec=1m
AccuracySec=1m
Persistent=true

[Install]
WantedBy=timers.target
""",
            }

            # Write all service and timer files
            for filename, content in services.items():
                file_path = self.runtime.systemd_dir / filename
                file_path.write_text(content)
                self.logger.info(f"Created systemd file: {file_path}")

            # Reload after writing the units so systemd sees the current generated files even
            # while first-run setup is still pending.
            if self.runtime.is_fake:
                return True, None
            self.run_command(['systemctl', 'daemon-reload'])

            if not activate_timers:
                for service_name in ['check_mount', 'check_health', 'backup_cloud', 'ddns_update']:
                    # Persistent timers replay missed runs as soon as they start. During first-run
                    # setup the config still has empty mount/rclone/email fields, so keep every
                    # generated recurring unit inactive until the wizard completes.
                    self.run_command(['systemctl', 'stop', f'{service_name}.timer'], check=False)
                    self.run_command(['systemctl', 'disable', f'{service_name}.timer'], check=False)
                    self.run_command(
                        ['systemctl', 'disable', f'{service_name}.service'], check=False
                    )
                    self.logger.info(
                        f"Generated {service_name} service and timer without activation"
                    )

                return True, None

            # Enable and start services and timers
            for service_name in ['check_mount', 'check_health', 'backup_cloud', 'ddns_update']:
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
