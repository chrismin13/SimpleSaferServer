import logging
import os
import re
import stat
import time
from datetime import datetime
from functools import wraps
from tempfile import NamedTemporaryFile

from flask import Blueprint, redirect, render_template, session

from simple_safer_server.adapters.command_runner import CalledProcessError, SubprocessError
from simple_safer_server.adapters.setup_commands import SetupCommandAdapter
from simple_safer_server.services.backup_drive_setup import (
    BackupDriveSetupError,
    _get_mounted_partitions_for_disk,
    apply_backup_drive_configuration,
    unmount_disk_partitions,
    unmount_selected_partition,
)
from simple_safer_server.services.backup_drive_setup import (
    list_available_drives as get_available_backup_drives,
)
from simple_safer_server.services.backup_drive_unmount import (
    is_selected_partition_managed_backup_drive,
    unmount_managed_backup_drive,
)
from simple_safer_server.services.cloud_backup_service import normalize_bandwidth_limit
from simple_safer_server.services.config_manager import ConfigManager
from simple_safer_server.services.runtime import get_fake_state, get_runtime
from simple_safer_server.services.smb_manager import SMBManager
from simple_safer_server.services.system_utils import SystemUtils
from simple_safer_server.services.user_manager import UserManager
from simple_safer_server.web.api import json_data, json_problem, json_request_data
from simple_safer_server.web.problems import (
    ApiProblem,
    ForbiddenProblem,
    OperationProblem,
    UnauthorizedProblem,
    ValidationProblem,
)

setup = Blueprint('setup', __name__)
runtime = get_runtime()
fake_state = get_fake_state() if runtime.is_fake else None
config_manager = ConfigManager(runtime=runtime)
system_utils = SystemUtils(runtime=runtime)
user_manager = UserManager(runtime=runtime)
smb_manager = SMBManager(runtime=runtime)
setup_command_adapter = SetupCommandAdapter()
logger = logging.getLogger(__name__)

# How long to wait for udev to create a newly-partitioned device node
# (e.g. /dev/nvme0n1p1) before giving up and reporting an error.
PARTITION_POLL_INTERVAL_SECONDS = 0.5  # delay between existence checks
PARTITION_POLL_TIMEOUT_SECONDS = 5.0  # maximum total wait


def _validation_problem(message, **extra):
    return json_problem(ValidationProblem(message, slug='setup-validation-error', extra=extra))


def _operation_problem(message, **extra):
    return json_problem(OperationProblem(message, slug='setup-operation-failed', extra=extra))


def _valid_tcp_port(value):
    text = str(value or '').strip()
    if not text.isdigit():
        return False
    port = int(text)
    return 1 <= port <= 65535


def setup_api_access_required(route_handler):
    """Allow anonymous setup API access only during first-time onboarding."""

    @wraps(route_handler)
    def wrapped(*args, **kwargs):
        # Once setup is complete these routes become admin maintenance tools,
        # so old bookmarked setup URLs must not keep working anonymously.
        if not config_manager.is_setup_complete():
            return route_handler(*args, **kwargs)

        if 'username' not in session:
            return json_problem(
                UnauthorizedProblem('Please log in again.', slug='setup-login-required')
            )

        # Reload user data to ensure admin checks use the latest persisted roles.
        user_manager.reload_users()
        if not user_manager.is_admin(session['username']):
            return json_problem(
                ForbiddenProblem('Admin privileges required.', slug='setup-admin-required')
            )

        return route_handler(*args, **kwargs)

    return wrapped


MANAGED_UNMOUNT_RETRY_ERROR = (
    'The selected partition is busy. If it is still serving the backup share over SMB, '
    'retry with the SMB-safe unmount path.'
)
MANAGED_UNMOUNT_RETRY_DETAILS = (
    'This retry may temporarily stop SMB access and related background backup tasks, '
    'unmount the configured backup share, and then restart SMB.'
)


def get_partition_node(disk):
    """Return the first-partition device node for *disk*.

    Linux names partition nodes differently depending on the disk type:
    - Standard SCSI/SATA disks (e.g. /dev/sdb)  → /dev/sdb1
    - NVMe and MMC devices whose path already ends in a digit
      (e.g. /dev/nvme0n1, /dev/mmcblk0)         → /dev/nvme0n1p1, /dev/mmcblk0p1

    The rule is: if the last character of the disk path is a digit, insert a
    'p' separator before the partition number so the kernel can tell where the
    disk name ends and the partition number begins.

    Raises ValueError if *disk* is not a non-empty string.
    """
    if not isinstance(disk, str) or not disk:
        raise ValueError(f"disk must be a non-empty string, got {disk!r}")
    if disk[-1].isdigit():
        return f"{disk}p1"
    return f"{disk}1"


def _get_configured_backup_drive_identity():
    return (
        config_manager.get_value('backup', 'mount_point', runtime.default_mount_point),
        config_manager.get_value('backup', 'uuid', ''),
    )


def _is_busy_unmount_error(error):
    return 'busy' in str(error).lower()


def _build_managed_unmount_retry_response(partition, configured_mount_point, configured_uuid):
    if not is_selected_partition_managed_backup_drive(
        partition,
        configured_mount_point,
        configured_uuid,
        system_utils,
        runtime=runtime,
    ):
        return None

    # This response only appears after the exact-partition unmount already
    # failed, so power users can make an explicit choice about stopping SMB.
    return ValidationProblem(
        MANAGED_UNMOUNT_RETRY_ERROR,
        slug='setup-managed-unmount-retry-available',
        extra={
            'details': MANAGED_UNMOUNT_RETRY_DETAILS,
            'can_retry_managed_unmount': True,
        },
    )


def _unmount_selected_partition_with_managed_retry(partition, force_managed=False):
    if force_managed:
        configured_mount_point, configured_uuid = _get_configured_backup_drive_identity()
        if not is_selected_partition_managed_backup_drive(
            partition,
            configured_mount_point,
            configured_uuid,
            system_utils,
            runtime=runtime,
        ):
            raise BackupDriveSetupError(
                'The selected partition is no longer the active configured backup drive.'
            )
        unmount_managed_backup_drive(
            configured_mount_point,
            configured_uuid,
            system_utils,
            runtime=runtime,
            power_down=False,
        )
        return (
            'Drive unmounted after the SMB-safe retry temporarily stopped SMB access '
            'and related background backup tasks.'
        )

    try:
        return unmount_selected_partition(partition, runtime=runtime)
    except BackupDriveSetupError as exc:
        if not _is_busy_unmount_error(exc):
            raise

        configured_mount_point, configured_uuid = _get_configured_backup_drive_identity()
        retry_response = _build_managed_unmount_retry_response(
            partition,
            configured_mount_point,
            configured_uuid,
        )
        if retry_response is not None:
            return retry_response
        raise


@setup.route('/setup')
def setup_page():
    """Render the setup wizard page"""
    try:
        current_config = config_manager.get_all_config()
        # Log section names only; setup config can include admin contact details
        # and managed service paths that do not belong in routine logs.
        logger.debug(
            "Checking setup status with config sections: %s", sorted(current_config.keys())
        )

        # Check if setup is complete
        if config_manager.is_setup_complete():
            logger.info("Setup is complete, redirecting to main page")
            return redirect('/')

        # Check if we have all required fields
        required_fields = {
            'system': ['username', 'server_name'],
            'backup': ['mount_point', 'uuid', 'email_address'],
            'schedule': ['backup_cloud_time'],
        }

        missing_fields = []
        for section, fields in required_fields.items():
            if section not in current_config:
                missing_fields.append(f"Missing section: {section}")
                continue
            for field in fields:
                if field not in current_config[section] or not current_config[section][field]:
                    missing_fields.append(f"Missing {section}.{field}")

        if missing_fields:
            logger.info(f"Setup incomplete, missing fields: {missing_fields}")
            return render_template('setup.html')

        # Do NOT mark setup as complete here. Only do so in /api/setup/complete.
        return render_template('setup.html')

    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error checking setup status: {e}")
        return render_template('setup.html')


@setup.route('/api/setup/user', methods=['POST'])
@setup_api_access_required
def create_user():
    """Create the initial admin user"""
    try:
        data = json_request_data()
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return _validation_problem('Username and password are required')

        success, message = user_manager.create_user(username, password, is_admin=True)
        if success:
            # Log in the user
            session['username'] = username
            return json_data()
        return _validation_problem(message)
    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        return _operation_problem('Could not create user')


@setup.route('/api/setup/format-drives', methods=['GET'])
@setup_api_access_required
def list_format_drives():
    """List disks for the destructive format step."""
    try:
        # Step 2 is intentionally broader than the mount pickers because it is
        # the "prepare or erase this disk" step, not the "pick an NTFS backup
        # partition" step.
        drives = get_available_backup_drives(runtime=runtime, ntfs_only=False)
        return json_data({'drives': drives})
    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error listing format drives: {e!s}")
        return _operation_problem(str(e))


@setup.route('/api/setup/mount-drives', methods=['GET'])
@setup_api_access_required
def list_mount_drives():
    """List NTFS partitions for the mount step."""
    try:
        # Step 3 is partition-oriented and only accepts NTFS backup targets, so
        # it must reuse the same NTFS scan as the Drive Health rerun flow. That
        # includes the blkid fallback when lsblk reports ntfs-3g mounts as
        # fuseblk, which is easy to miss if this route ever gets "simplified".
        drives = get_available_backup_drives(runtime=runtime, ntfs_only=True)
        return json_data({'drives': drives})
    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error listing mount drives: {e!s}")
        return _operation_problem(str(e))


@setup.route('/api/setup/format', methods=['POST'])
@setup_api_access_required
def format_drive():
    """Format the selected drive"""
    try:
        if runtime.is_fake:
            return _validation_problem(
                'Formatting is disabled in fake mode',
                details='Fake mode never formats local disks. Use the mount step to point the backup source at an existing folder instead.',
            )

        data = json_request_data()
        # Step 2 is intentionally disk-oriented because formatting and partition
        # creation are destructive whole-disk operations.
        disk = data.get('disk')

        # Treat an absent key and an explicit null the same way.  Falsey but
        # non-None values (e.g. 0, False, []) must fall through to the
        # isinstance check below so they get the clearer "must be a string"
        # error instead of the generic "No disk selected" message.
        if disk is None:
            return _validation_problem('No disk selected')

        # A JSON client could send a non-string value (e.g. 123 or False);
        # os.path.realpath would raise TypeError, so we catch it here.
        if not isinstance(disk, str):
            return _validation_problem('Invalid disk path: must be a string')

        # Reject an empty string after the type check — the `disk is None` guard
        # above only catches a missing key; an explicit empty string must be
        # rejected here.
        if not disk:
            return _validation_problem('No disk selected')

        # Resolve symlinks first so a symlink inside /dev/ pointing elsewhere
        # cannot be used to bypass the /dev/ prefix check, then verify the
        # caller is targeting an existing whole-disk block device.
        disk = os.path.realpath(disk)
        if not disk.startswith('/dev/'):
            return _validation_problem('Invalid disk path: must be a /dev/ device node')

        # Use os.stat() directly so the error message reflects the actual
        # failure: a missing node (FileNotFoundError) is different from a
        # permission problem (PermissionError), and os.path.exists() silently
        # maps both to False, which would produce a misleading "does not exist"
        # message when the real issue is a permissions error.
        try:
            disk_stat = os.stat(disk)
        except FileNotFoundError:
            return _validation_problem('Invalid disk path: device does not exist')
        except PermissionError:
            return _validation_problem(
                'Invalid disk path: permission denied while inspecting device node'
            )
        except OSError:
            return _validation_problem('Invalid disk path: unable to inspect device node')

        if not stat.S_ISBLK(disk_stat.st_mode):
            return _validation_problem('Invalid disk path: must be a block device node')

        # Confirm the node is a whole disk rather than a partition (e.g. /dev/sda
        # has TYPE=disk; /dev/sda1 has TYPE=part).  Passing a partition path here
        # would corrupt get_partition_node output (e.g. /dev/sda1 → /dev/sda11).
        try:
            lsblk_result = setup_command_adapter.whole_disk_type(disk)
        except (SubprocessError, OSError):
            return _validation_problem('Unable to verify disk type')

        if lsblk_result.stdout.strip() != 'disk':
            return _validation_problem('Invalid disk path: must be a whole-disk block device')

        mounted_partitions = _get_mounted_partitions_for_disk(disk)

        if mounted_partitions:
            partition_info = '\n'.join(
                [f"- {p['device']} at {p['mount_point']}" for p in mounted_partitions]
            )
            return _validation_problem(
                'Drive has mounted partitions',
                details=f'The following partitions are currently mounted:\n{partition_info}\n\nPlease unmount all partitions before formatting.',
                can_unmount=True,
            )

        # Determine the correct first-partition device node.
        # NVMe/MMC paths end in a digit (e.g. /dev/nvme0n1), so their partition
        # nodes use a 'p' separator (e.g. /dev/nvme0n1p1).  Standard SCSI/SATA
        # disks (e.g. /dev/sdb) just append the number (e.g. /dev/sdb1).
        partition = get_partition_node(disk)
        if not os.path.exists(partition):
            # Create partition using fdisk
            fdisk_input = "n\np\n1\n\n\nw\n"
            result = setup_command_adapter.create_partition(disk, fdisk_input.encode())
            if result.returncode != 0:
                return _operation_problem(
                    'Failed to create partition',
                    details='Could not create partition on the drive. Please ensure the drive is not in use.',
                )

            # Ask the kernel to re-read the partition table so the new partition
            # node (e.g. /dev/nvme0n1p1) appears in /dev before mkfs.ntfs runs.
            # partprobe failures are non-fatal: mkfs.ntfs will still succeed on
            # most kernels without it, but we log at debug so failures are
            # visible if troubleshooting a race condition.
            try:
                result_probe = setup_command_adapter.partprobe(disk)
                if result_probe.returncode != 0:
                    logger.debug(
                        "partprobe %s exited %d: %s",
                        disk,
                        result_probe.returncode,
                        result_probe.stderr.strip(),
                    )
            except OSError as e:
                logger.debug("partprobe failed for %s; continuing without it: %s", disk, e)

            # Poll for up to 5 seconds so udev has time to create the new
            # device node before mkfs.ntfs tries to open it.  Without this
            # wait, mkfs can fail with "No such file or directory" on kernels
            # where udev processing is slightly delayed.
            deadline = time.monotonic() + PARTITION_POLL_TIMEOUT_SECONDS
            while True:
                # Verify the node exists *and* is a block device — udev could
                # briefly create a placeholder file of the wrong type.
                try:
                    is_block_device = stat.S_ISBLK(os.stat(partition).st_mode)
                except OSError:
                    is_block_device = False
                if is_block_device:
                    break
                if time.monotonic() >= deadline:
                    return _operation_problem(
                        'Partition node did not appear after partitioning',
                        details=(
                            f'{partition} was not created within '
                            f'{PARTITION_POLL_TIMEOUT_SECONDS:.0f} seconds of partitioning. '
                            'The kernel may not have processed the new partition table yet. '
                            'Please try again.'
                        ),
                    )
                time.sleep(PARTITION_POLL_INTERVAL_SECONDS)

        # Verify the partition node immediately before formatting so both the
        # "already existed" and "just created" paths are protected.
        deadline = time.monotonic() + PARTITION_POLL_TIMEOUT_SECONDS
        while True:
            try:
                partition_lstat = os.lstat(partition)
                is_symlink = stat.S_ISLNK(partition_lstat.st_mode)
                is_block_device = (not is_symlink) and stat.S_ISBLK(os.stat(partition).st_mode)
            except OSError:
                is_block_device = False
            if is_block_device:
                break
            if time.monotonic() >= deadline:
                return _validation_problem(
                    'Invalid partition path: must be a partition block device',
                    details=(
                        f'{partition} was not a valid block device within '
                        f'{PARTITION_POLL_TIMEOUT_SECONDS:.0f} seconds. '
                        'Please verify the drive path and try again.'
                    ),
                )
            time.sleep(PARTITION_POLL_INTERVAL_SECONDS)
        # Format the partition as NTFS
        result = setup_command_adapter.format_ntfs(partition)

        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else 'Unknown error occurred'
            return _operation_problem(
                f'Error formatting partition: {error_msg}',
                details='Please ensure the drive is not in use and try again.',
            )

        return json_data()

    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error formatting drive: {e!s}")
        return _operation_problem(
            'Error formatting drive',
            details='An unexpected error occurred. Please check the system logs for more information.',
        )


@setup.route('/api/setup/unmount', methods=['POST'])
@setup_api_access_required
def unmount_drive():
    """Unmount the selected drive"""
    try:
        data = json_request_data()
        # The setup wizard uses this route for two different UI controls:
        # whole-disk unmount before formatting, and exact-partition unmount
        # before mounting an NTFS partition in step 3.
        disk = data.get('disk')
        partition = data.get('partition')
        force_managed = bool(data.get('force_managed'))
        if disk:
            message = unmount_disk_partitions(disk, runtime=runtime)
        else:
            message = _unmount_selected_partition_with_managed_retry(
                partition,
                force_managed=force_managed,
            )

        if isinstance(message, ValidationProblem):
            return json_problem(message)
        return json_data(message=message)
    except BackupDriveSetupError as e:
        return _validation_problem(str(e), details=e.details)
    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error unmounting drive: {e!s}")
        return _operation_problem(
            f'Error unmounting drive: {e!s}',
            details='An unexpected error occurred. Please check the system logs for more information.',
        )


@setup.route('/api/setup/mount', methods=['POST'])
@setup_api_access_required
def mount_drive():
    """Mount the selected drive"""
    try:
        data = json_request_data()
        # Step 3 always selects a filesystem-bearing partition, never a whole
        # disk. That aligns it with the rerun flow on Drive Health.
        partition = data.get('partition')
        if not partition:
            return _validation_problem('partition is required')
        mount_point = data.get('mount_point') or runtime.default_mount_point
        auto_mount = data.get('auto_mount', True)
        result = apply_backup_drive_configuration(
            partition,
            mount_point,
            auto_mount,
            config_manager,
            smb_manager,
            runtime=runtime,
        )
        logger.info(
            "Backup drive mounted successfully at %s", result.get('mount_point', mount_point)
        )
        return json_data(message=result['message'])
    except BackupDriveSetupError as e:
        return _validation_problem(str(e), details=e.details)
    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error mounting drive: {e!s}")
        return _operation_problem(
            f'Error mounting drive: {e!s}',
            details='An unexpected error occurred. Please check the system logs for more information.',
        )


@setup.route('/api/setup/rclone', methods=['POST'])
@setup_api_access_required
def setup_rclone():
    """Set up rclone configuration"""
    try:
        data = json_request_data()
        config = data.get('config')
        remote_name = data.get('remote_name')

        if not config or not remote_name:
            return _validation_problem('Config and remote name are required')

        # Store rclone config
        if not system_utils.setup_rclone(config):
            return _operation_problem('Failed to set up rclone')

        # Save to config
        config_manager.set_value('backup', 'rclone_dir', remote_name)

        return json_data()
    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error setting up rclone: {e}")
        return _operation_problem('Could not set up rclone')


@setup.route('/api/setup/email', methods=['POST'])
@setup_api_access_required
def setup_email():
    """Set up email configuration"""
    try:
        data = json_request_data()
        # SMTP credentials can be entered during setup, so keep raw payloads out of logs.
        logger.info("Received email setup request")

        email = data.get('emailAddress')
        from_address = data.get('fromAddress')
        smtp_server = data.get('smtpServer')
        smtp_port = data.get('smtpPort')
        smtp_username = data.get('smtpUsername')
        smtp_password = data.get('smtpPassword')

        if not all([email, from_address, smtp_server, smtp_port, smtp_username, smtp_password]):
            logger.error("Missing email fields")
            return _validation_problem('All email fields are required')
        if not _valid_tcp_port(smtp_port):
            return _validation_problem('SMTP port must be between 1 and 65535')

        if not system_utils.write_msmtp_config(
            from_address, smtp_server, smtp_port, smtp_username, smtp_password
        ):
            return _operation_problem('Failed to write msmtp configuration')

        # Persist the UI-facing addresses only after msmtp is safely written.
        config_manager.set_value('backup', 'email_address', email)
        config_manager.set_value('backup', 'from_address', from_address)

        return json_data()
    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error setting up email: {e}")
        return _operation_problem('Could not save email settings')


@setup.route('/api/setup/schedule', methods=['POST'])
@setup_api_access_required
def save_schedule():
    """Save the backup schedule configuration"""
    try:
        data = json_request_data()
        schedule_time = data.get('time')
        bandwidth_limit = normalize_bandwidth_limit(data.get('bandwidth_limit', ''))

        if not schedule_time:
            return _validation_problem('Missing required fields', details='Time is required')

        # Validate time format (HH:MM)
        if not re.match(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$', schedule_time):
            return _validation_problem(
                'Invalid time format',
                details='Time must be in HH:MM format (24-hour)',
            )

        # Save schedule to config
        config_manager.set_value('schedule', 'backup_cloud_time', schedule_time)
        if bandwidth_limit is not None:
            config_manager.set_value('backup', 'bandwidth_limit', bandwidth_limit)

        logger.info(f"Schedule saved: daily at {schedule_time}, bandwidth limit: {bandwidth_limit}")
        return json_data(message='Backup settings saved successfully')

    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error saving schedule: {e!s}")
        return _operation_problem(
            f'Error saving schedule: {e!s}',
            details='An unexpected error occurred. Please check the system logs for more information.',
        )


def install_systemd_tasks(config):
    """Generate and install systemd service/timer files for all main tasks."""
    try:
        if runtime.is_fake:
            return True, None

        # Create the systemd configuration file
        ok, err = system_utils.create_systemd_config_file(config)
        if not ok:
            return False, f"Failed to create systemd config file: {err}"

        # Install the scripts to /usr/local/bin/
        ok, err = system_utils.install_systemd_scripts(config)
        if not ok:
            return False, f"Failed to install systemd scripts: {err}"

        # Install systemd services and timers
        ok, err = system_utils.install_systemd_services_and_timers(config)
        if not ok:
            return False, f"Failed to install systemd services and timers: {err}"

        return True, None
    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error installing systemd tasks: {e}")
        return False, str(e)


def setup_smb_share(config):
    """Set up SMB share configuration"""
    try:
        backup = config.get('backup', {})
        mount_point = backup.get('mount_point', runtime.default_mount_point)
        system = config.get('system', {})
        admin_username = system.get('username', 'admin')

        if runtime.is_fake:
            smb_manager.ensure_default_backup_share(
                mount_point,
                admin_username,
                fake_mode_comment='Fake-mode backup share',
            )
            return True, None

        if admin_username not in user_manager.users:
            return False, f"Admin user {admin_username} not found in user database"

        # Ensure admin user exists in Samba
        if not user_manager.user_exists_in_samba(admin_username):
            return False, (
                f"Admin user {admin_username} is missing from Samba. "
                "The setup flow does not store plaintext passwords, so the Samba account cannot be recreated automatically. "
                "Recreate the admin user through the setup flow or reset the Samba password manually."
            )

        smb_manager.ensure_default_backup_share(mount_point, admin_username)
        logger.info("Ensured the SimpleSaferServer-managed backup share points at %s", mount_point)

        # Enable SMB services to start on boot
        try:
            setup_command_adapter.enable_smb_unit('smbd')
            setup_command_adapter.enable_smb_unit('nmbd')
            logger.info("SMB services enabled for boot")
        except (CalledProcessError, OSError) as e:
            logger.error(f"Failed to enable SMB services: {e}")
            # Don't fail setup for this, just log it

        logger.info(
            "SMB share setup completed successfully. Share 'backup' is configured at %s",
            mount_point,
        )
        return True, None

    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error setting up SMB share: {e}")
        return False, str(e)


@setup.route('/api/setup/complete', methods=['POST'])
@setup_api_access_required
def complete_setup():
    """Complete the setup process"""
    try:
        current_config = config_manager.get_all_config()
        # The validation loop below logs only missing section/field names.
        logger.debug("Completing setup after loading current configuration")

        # Validate required fields
        required_fields = {
            'system': ['username', 'server_name'],
            'backup': ['mount_point', 'uuid', 'email_address'],
            'schedule': ['backup_cloud_time'],
        }

        missing_fields = []
        for section, fields in required_fields.items():
            if section not in current_config:
                logger.error(f"Missing section in config: {section}")
                missing_fields.append(f"Missing section: {section}")
                continue
            for field in fields:
                if field not in current_config[section] or not current_config[section][field]:
                    logger.error(f"Missing field in {section}: {field}")
                    missing_fields.append(f"Missing {section}.{field}")

        if missing_fields:
            logger.error(f"Setup validation failed. Missing fields: {missing_fields}")
            return _validation_problem('Missing required fields', details=missing_fields)

        # Update the user's last login time since they completed the setup
        if 'username' in session:
            username = session['username']
            if username in user_manager.users:
                user_manager.users[username]['last_login'] = str(datetime.utcnow())
                user_manager._save_users()
                logger.info(f"Updated last login time for user {username} after setup completion")

        # Install systemd services and timers
        ok, err = install_systemd_tasks(current_config)
        if not ok:
            return _operation_problem(f'Failed to install systemd tasks: {err}')

        # Set up SMB share
        ok, err = setup_smb_share(current_config)
        if not ok:
            return _operation_problem(f'Failed to set up SMB share: {err}')

        # Mark setup as complete AFTER all systemd tasks are installed
        config_manager.mark_setup_complete()
        config_manager.load_config()  # Ensure in-memory config is up to date

        logger.info(
            "Setup completed successfully, systemd tasks installed, and SMB share configured."
        )
        return json_data()

    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error completing setup: {e!s}")
        return _operation_problem(
            'Error completing setup',
            details='An unexpected error occurred. Please check the system logs for more information.',
        )


@setup.route('/api/setup/system', methods=['POST'])
@setup_api_access_required
def setup_system_info():
    """Save system-level info such as username and server name"""
    try:
        data = json_request_data()
        username = data.get('username')
        server_name = data.get('server_name')

        if not username or not server_name:
            return _validation_problem('Username and server name are required')

        config_manager.set_value('system', 'username', username)
        config_manager.set_value('system', 'server_name', server_name)
        return json_data()
    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error saving system info: {e}")
        return _operation_problem('Could not save system information')


@setup.route('/api/setup/mega/connect', methods=['POST'])
@setup_api_access_required
def mega_connect():
    """Authenticate with MEGA and list folders using rclone."""
    try:
        data = json_request_data()
        email = data.get('email')
        password = data.get('password')
        if not email or not password:
            return _validation_problem('Email and password are required.')
        # Obscure password using rclone
        obscured_pw = setup_command_adapter.obscure_rclone_password(password)
        # Build temp rclone config
        config_text = f"""
[mega]
type = mega
user = {email}
pass = {obscured_pw}
"""
        with NamedTemporaryFile(
            delete=False, mode="w", prefix="rclone-", suffix=".conf"
        ) as config_file:
            config_file.write(config_text)
            config_path = config_file.name
        try:
            # List folders at root
            lsjson = setup_command_adapter.rclone_lsjson("mega:/", config_path)
            if lsjson.returncode != 0:
                return _validation_problem('Failed to list MEGA folders. Check credentials.')
            import json as pyjson

            items = pyjson.loads(lsjson.stdout)
            folders = [item['Name'] for item in items if item['IsDir']]
            return json_data({'folders': folders})
        finally:
            os.remove(config_path)
    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error connecting to MEGA: {e!s}")
        return _operation_problem('Error connecting to MEGA')


@setup.route('/api/setup/mega/list_folders', methods=['POST'])
@setup_api_access_required
def mega_list_folders():
    """List folders at a given MEGA path using rclone."""
    try:
        data = json_request_data()
        path = data.get('path', '/')
        email = data.get('email')
        password = data.get('password')
        if not email or not password:
            return _validation_problem('Email and password are required.')
        obscured_pw = setup_command_adapter.obscure_rclone_password(password)
        config_text = f"""
[mega]
type = mega
user = {email}
pass = {obscured_pw}
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(
            delete=False, mode="w", prefix="rclone-", suffix=".conf"
        ) as config_file:
            config_file.write(config_text)
            config_path = config_file.name
        try:
            lsjson = setup_command_adapter.rclone_lsjson(f"mega:{path}", config_path)
            if lsjson.returncode != 0:
                return _validation_problem(
                    'Failed to list MEGA folders. Check credentials or path.'
                )
            import json as pyjson

            items = pyjson.loads(lsjson.stdout)
            folders = [item['Name'] for item in items if item['IsDir']]
            # Compute parent path
            parent = '/'.join(path.rstrip('/').split('/')[:-1]) or '/'
            return json_data({'folders': folders, 'path': path, 'parent': parent})
        finally:
            os.remove(config_path)
    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error listing MEGA folders: {e!s}")
        return _operation_problem('Error listing MEGA folders')


@setup.route('/api/setup/mega/create_folder', methods=['POST'])
@setup_api_access_required
def mega_create_folder_picker():
    """Create a new folder at a given MEGA path using rclone."""
    try:
        data = json_request_data()
        folder_name = data.get('folder_name')
        path = data.get('path', '/')
        email = data.get('email')
        password = data.get('password')
        if not folder_name or not email or not password:
            return _validation_problem('Folder name, email, and password are required.')
        obscured_pw = setup_command_adapter.obscure_rclone_password(password)
        config_text = f"""
[mega]
type = mega
user = {email}
pass = {obscured_pw}
"""
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(
            delete=False, mode="w", prefix="rclone-", suffix=".conf"
        ) as config_file:
            config_file.write(config_text)
            config_path = config_file.name
        try:
            # Create folder at mega:{path}/{folder_name}
            full_path = f"{path.rstrip('/')}/{folder_name}" if path != '/' else f"/{folder_name}"
            mkdir = setup_command_adapter.rclone_mkdir(f"mega:{full_path}", config_path)
            if mkdir.returncode != 0:
                return _validation_problem('Failed to create folder on MEGA.')
            return json_data()
        finally:
            os.remove(config_path)
    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error creating MEGA folder: {e!s}")
        return _operation_problem('Error creating folder')


@setup.route('/api/setup/mega/save', methods=['POST'])
@setup_api_access_required
def mega_save():
    """Save MEGA config (obscured password, selected folder) securely and write rclone config."""
    try:
        data = json_request_data()
        email = data.get('email')
        password = data.get('password')
        folder = data.get('folder')
        if not email or not password or not folder:
            return _validation_problem('Email, password, and folder are required.')
        obscured_pw = setup_command_adapter.obscure_rclone_password(password)
        # Write rclone config for MEGA
        mega_rclone_config = f"""[mega]\ntype = mega\nuser = {email}\npass = {obscured_pw}\n"""
        if not system_utils.setup_rclone(mega_rclone_config):
            return _operation_problem('Failed to write rclone config for MEGA')
        # Persist after rclone is written so the UI does not advertise a cloud
        # target that the backup scripts cannot actually use.
        config_manager.set_value('backup', 'cloud_mode', 'mega')
        config_manager.set_value('backup', 'mega_email', email)
        config_manager.set_value('backup', 'mega_pass', obscured_pw)
        config_manager.set_value('backup', 'mega_folder', folder)
        config_manager.set_value('backup', 'rclone_dir', f"mega:{folder}")
        return json_data()
    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error saving MEGA config: {e!s}")
        return _operation_problem('Error saving MEGA config')
