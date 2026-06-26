import logging
import re

from simple_safer_server.adapters.command_runner import CalledProcessError, CommandRunner
from simple_safer_server.services.runtime import get_fake_state, get_runtime
from simple_safer_server.services.schedule_time import normalize_ui_schedule_time

SYSTEM_COMMAND_TIMEOUT_SECONDS = 30


class SystemUtils:
    def __init__(self, runtime=None, command_runner=None):
        self.runtime = runtime or get_runtime()
        self.command_runner = command_runner or CommandRunner()
        self.fake_state = get_fake_state() if self.runtime.is_fake else None
        self.logger = logging.getLogger(__name__)

    def run_command(self, command, check=True):
        """Run a system command and return the result"""
        try:
            result = self.command_runner.run(
                command,
                check=check,
                capture_output=True,
                text=True,
                timeout=SYSTEM_COMMAND_TIMEOUT_SECONDS,
            )
            return result.stdout.strip()
        except CalledProcessError as e:
            self.logger.error(f"Command failed: {e.stderr}")
            raise

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

    def validate_worker_task_config(self, config):
        """Validate worker schedule config without creating feature systemd units."""
        try:
            schedule = config.get('schedule', {})
            normalize_ui_schedule_time(schedule.get('backup_cloud_time', '03:00'))
            self.logger.info("Worker-managed task schedules validated")
            return True, None

        except Exception as e:
            self.logger.error(f"Error validating worker task schedules: {e}")
            return False, str(e)
