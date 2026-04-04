from flask import Blueprint, render_template, jsonify, request, redirect, session
from backup_drive_setup import (
    BackupDriveSetupError,
    apply_backup_drive_configuration,
    list_available_drives as get_available_backup_drives,
    _get_mounted_partitions_for_disk,
    unmount_disk_partitions,
    unmount_selected_partition,
)
from backup_drive_unmount import (
    is_selected_partition_managed_backup_drive,
    unmount_managed_backup_drive,
)
from config_manager import ConfigManager
from system_utils import SystemUtils
from user_manager import UserManager
from smb_manager import SMBManager
import logging
import subprocess
import os
import re
import stat
import time
from datetime import datetime
from functools import wraps
from tempfile import NamedTemporaryFile
from pathlib import Path
from runtime import get_runtime, get_fake_state

setup = Blueprint('setup', __name__)
runtime = get_runtime()
fake_state = get_fake_state() if runtime.is_fake else None
config_manager = ConfigManager(runtime=runtime)
system_utils = SystemUtils(runtime=runtime)
user_manager = UserManager(runtime=runtime)
smb_manager = SMBManager(runtime=runtime)
logger = logging.getLogger(__name__)

# How long to wait for udev to create a newly-partitioned device node
# (e.g. /dev/nvme0n1p1) before giving up and reporting an error.
PARTITION_POLL_INTERVAL_SECONDS = 0.5  # delay between existence checks
PARTITION_POLL_TIMEOUT_SECONDS = 5.0   # maximum total wait


def setup_api_access_required(route_handler):
    """Allow anonymous setup API access only during first-time onboarding."""
    @wraps(route_handler)
    def wrapped(*args, **kwargs):
        # Once setup is complete these routes become admin maintenance tools,
        # so old bookmarked setup URLs must not keep working anonymously.
        if not config_manager.is_setup_complete():
            return route_handler(*args, **kwargs)

        if 'username' not in session:
            return jsonify({'success': False, 'error': 'Please log in again.'}), 401

        # Reload user data to ensure we have the latest
        user_manager.users = user_manager._load_users()
        if not user_manager.is_admin(session['username']):
            return jsonify({'success': False, 'error': 'Admin privileges required.'}), 403

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

    Raises ValueError if *disk* is None or empty.
    """
    if not disk:
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
    return {
        'success': False,
        'error': MANAGED_UNMOUNT_RETRY_ERROR,
        'details': MANAGED_UNMOUNT_RETRY_DETAILS,
        'can_retry_managed_unmount': True,
    }


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
        # Get current config
        current_config = config_manager.get_all_config()
        logger.info(f"Current config during setup check: {current_config}")
        
        # Check if setup is complete
        if config_manager.is_setup_complete():
            logger.info("Setup is complete, redirecting to main page")
            return redirect('/')
        
        # Check if we have all required fields
        required_fields = {
            'system': ['username', 'server_name'],
            'backup': ['mount_point', 'uuid', 'email_address'],
            'schedule': ['backup_cloud_time']
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
        
    except Exception as e:
        logger.error(f"Error checking setup status: {e}")
        return render_template('setup.html')

@setup.route('/api/setup/user', methods=['POST'])
@setup_api_access_required
def create_user():
    """Create the initial admin user"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'success': False, 'error': 'Username and password are required'})
        
        success, message = user_manager.create_user(username, password)
        if success:
            # Log in the user
            session['username'] = username
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': message})
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        return jsonify({'success': False, 'error': str(e)})

@setup.route('/api/setup/format-drives', methods=['GET'])
@setup_api_access_required
def list_format_drives():
    """List disks for the destructive format step."""
    try:
        # Step 2 is intentionally broader than the mount pickers because it is
        # the "prepare or erase this disk" step, not the "pick an NTFS backup
        # partition" step.
        drives = get_available_backup_drives(runtime=runtime, ntfs_only=False)
        return jsonify({'success': True, 'drives': drives})
    except Exception as e:
        logger.error(f"Error listing format drives: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})


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
        return jsonify({'success': True, 'drives': drives})
    except Exception as e:
        logger.error(f"Error listing mount drives: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@setup.route('/api/setup/format', methods=['POST'])
@setup_api_access_required
def format_drive():
    """Format the selected drive"""
    try:
        if runtime.is_fake:
            return jsonify({
                'success': False,
                'error': 'Formatting is disabled in fake mode',
                'details': 'Fake mode never formats local disks. Use the mount step to point the backup source at an existing folder instead.'
            })

        data = request.get_json()
        # Step 2 is intentionally disk-oriented because formatting and partition
        # creation are destructive whole-disk operations.
        disk = data.get('disk')

        if not disk:
            return jsonify({'success': False, 'error': 'No disk selected'})

        # Resolve symlinks first so a symlink inside /dev/ pointing elsewhere
        # cannot be used to bypass the /dev/ prefix check, then validate that
        # the caller is actually targeting a block device node.
        disk = os.path.realpath(disk)
        if not disk.startswith('/dev/'):
            return jsonify({'success': False, 'error': 'Invalid disk path: must be a /dev/ device node'})

        mounted_partitions = _get_mounted_partitions_for_disk(disk)

        if mounted_partitions:
            partition_info = '\n'.join([f"- {p['device']} at {p['mount_point']}" for p in mounted_partitions])
            return jsonify({
                'success': False, 
                'error': 'Drive has mounted partitions',
                'details': f'The following partitions are currently mounted:\n{partition_info}\n\nPlease unmount all partitions before formatting.',
                'can_unmount': True
            })

        # Determine the correct first-partition device node.
        # NVMe/MMC paths end in a digit (e.g. /dev/nvme0n1), so their partition
        # nodes use a 'p' separator (e.g. /dev/nvme0n1p1).  Standard SCSI/SATA
        # disks (e.g. /dev/sdb) just append the number (e.g. /dev/sdb1).
        partition = get_partition_node(disk)
        if not os.path.exists(partition):
            # Create partition using fdisk
            fdisk_input = f"n\np\n1\n\n\nw\n"
            result = subprocess.run(['fdisk', disk], input=fdisk_input.encode(), capture_output=True)
            if result.returncode != 0:
                return jsonify({
                    'success': False,
                    'error': 'Failed to create partition',
                    'details': 'Could not create partition on the drive. Please ensure the drive is not in use.'
                })

            # Ask the kernel to re-read the partition table so the new partition
            # node (e.g. /dev/nvme0n1p1) appears in /dev before mkfs.ntfs runs.
            # partprobe failures are non-fatal: mkfs.ntfs will still succeed on
            # most kernels without it, but we log at debug so failures are
            # visible if troubleshooting a race condition.
            try:
                result_probe = subprocess.run(['partprobe', disk], capture_output=True, text=True)
                if result_probe.returncode != 0:
                    logger.debug(
                        "partprobe %s exited %d: %s",
                        disk, result_probe.returncode, result_probe.stderr.strip(),
                    )
            except FileNotFoundError:
                logger.debug("partprobe not found for %s; continuing without it", disk)
            except subprocess.SubprocessError as exc:
                logger.debug("partprobe failed for %s: %s", disk, exc)

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
                    return jsonify({
                        'success': False,
                        'error': 'Partition node did not appear after partitioning',
                        'details': (
                            f'{partition} was not created within '
                            f'{PARTITION_POLL_TIMEOUT_SECONDS:.0f} seconds of partitioning. '
                            'The kernel may not have processed the new partition table yet. '
                            'Please try again.'
                        ),
                    })
                time.sleep(PARTITION_POLL_INTERVAL_SECONDS)

        # Format the partition as NTFS
        result = subprocess.run(['mkfs.ntfs', '-f', partition], capture_output=True, text=True)

        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else 'Unknown error occurred'
            return jsonify({
                'success': False,
                'error': f'Error formatting partition: {error_msg}',
                'details': 'Please ensure the drive is not in use and try again.'
            })

        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error formatting drive: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Error formatting drive: {str(e)}',
            'details': 'An unexpected error occurred. Please check the system logs for more information.'
        })

@setup.route('/api/setup/unmount', methods=['POST'])
@setup_api_access_required
def unmount_drive():
    """Unmount the selected drive"""
    try:
        data = request.get_json() or {}
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

        if isinstance(message, dict):
            return jsonify(message)
        return jsonify({'success': True, 'message': message})
    except BackupDriveSetupError as e:
        return jsonify({'success': False, 'error': str(e), 'details': e.details})
    except Exception as e:
        logger.error(f"Error unmounting drive: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Error unmounting drive: {str(e)}',
            'details': 'An unexpected error occurred. Please check the system logs for more information.'
        })

@setup.route('/api/setup/mount', methods=['POST'])
@setup_api_access_required
def mount_drive():
    """Mount the selected drive"""
    try:
        # silent=True prevents a 415 exception when Content-Type is absent or
        # wrong, returning None instead so the `or {}` guard can take over.
        data = request.get_json(silent=True) or {}
        # Step 3 always selects a filesystem-bearing partition, never a whole
        # disk. That aligns it with the rerun flow on Drive Health.
        partition = data.get('partition')
        if not partition:
            return jsonify({'success': False, 'error': 'partition is required'}), 400
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
        logger.info(f"Current config after mounting: {config_manager.get_all_config()}")
        return jsonify({'success': True, 'message': result['message']})
    except BackupDriveSetupError as e:
        return jsonify({'success': False, 'error': str(e), 'details': e.details})
    except Exception as e:
        logger.error(f"Error mounting drive: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Error mounting drive: {str(e)}',
            'details': 'An unexpected error occurred. Please check the system logs for more information.'
        })

@setup.route('/api/setup/rclone', methods=['POST'])
@setup_api_access_required
def setup_rclone():
    """Set up rclone configuration"""
    try:
        data = request.get_json()
        config = data.get('config')
        remote_name = data.get('remote_name')
        
        if not config or not remote_name:
            return jsonify({'success': False, 'error': 'Config and remote name are required'})
        
        # Store rclone config
        if not system_utils.setup_rclone(config):
            return jsonify({'success': False, 'error': 'Failed to set up rclone'})
        
        # Save to config
        config_manager.set_value('backup', 'rclone_dir', remote_name)
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error setting up rclone: {e}")
        return jsonify({'success': False, 'error': str(e)})

@setup.route('/api/setup/email', methods=['POST'])
@setup_api_access_required
def setup_email():
    """Set up email configuration"""
    try:
        data = request.get_json()
        logger.info(f"Received email setup data: {data}")
        
        email = data.get('emailAddress')
        from_address = data.get('fromAddress')
        smtp_server = data.get('smtpServer')
        smtp_port = data.get('smtpPort')
        smtp_username = data.get('smtpUsername')
        smtp_password = data.get('smtpPassword')
        
        if not all([email, from_address, smtp_server, smtp_port, smtp_username, smtp_password]):
            logger.error("Missing email fields")
            return jsonify({'success': False, 'error': 'All email fields are required'})
        
        # Save email to config and write /etc/msmtprc
        config_manager.set_value('backup', 'email_address', email)
        config_manager.set_value('backup', 'from_address', from_address)

        if not system_utils.write_msmtp_config(from_address, smtp_server, smtp_port, smtp_username, smtp_password):
            return jsonify({'success': False, 'error': 'Failed to write msmtp configuration'})

        # Verify the config was saved
        current_config = config_manager.get_all_config()
        logger.info(f"Current config after email setup: {current_config}")
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error setting up email: {e}")
        return jsonify({'success': False, 'error': str(e)})

@setup.route('/api/setup/schedule', methods=['POST'])
@setup_api_access_required
def save_schedule():
    """Save the backup schedule configuration"""
    try:
        data = request.get_json()
        time = data.get('time')
        bandwidth_limit = data.get('bandwidth_limit', '')
        
        if not time:
            return jsonify({
                'success': False,
                'error': 'Missing required fields',
                'details': 'Time is required'
            })

        # Validate time format (HH:MM)
        if not re.match(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$', time):
            return jsonify({
                'success': False,
                'error': 'Invalid time format',
                'details': 'Time must be in HH:MM format (24-hour)'
            })

        # Save schedule to config
        config_manager.set_value('schedule', 'backup_cloud_time', time)
        if bandwidth_limit is not None:
            config_manager.set_value('backup', 'bandwidth_limit', bandwidth_limit)
        
        logger.info(f"Schedule saved: daily at {time}, bandwidth limit: {bandwidth_limit}")
        return jsonify({
            'success': True,
            'message': 'Backup settings saved successfully'
        })

    except Exception as e:
        logger.error(f"Error saving schedule: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Error saving schedule: {str(e)}',
            'details': 'An unexpected error occurred. Please check the system logs for more information.'
        })

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
            existing_shares = smb_manager.get_shares()
            backup_share_exists = any(share['name'] == 'backup' for share in existing_shares)
            if backup_share_exists:
                smb_manager.update_share(
                    old_name='backup',
                    new_name='backup',
                    path=mount_point,
                    writable=True,
                    comment='Fake-mode backup share',
                    valid_users=[admin_username]
                )
            else:
                smb_manager.add_share(
                    name='backup',
                    path=mount_point,
                    writable=True,
                    comment='Fake-mode backup share',
                    valid_users=[admin_username]
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
        
        # Check if backup share already exists and update it, or create new one
        existing_shares = smb_manager.get_shares()
        backup_share_exists = any(share['name'] == 'backup' for share in existing_shares)
        
        if backup_share_exists:
            # Update existing backup share
            smb_manager.update_share(
                old_name='backup',
                new_name='backup',
                path=mount_point,
                writable=True,
                comment='Default backup share created by SimpleSaferServer setup',
                valid_users=[admin_username]
            )
            logger.info(f"Updated existing backup share at {mount_point}")
        else:
            # Create new backup share
            smb_manager.add_share(
                name='backup',
                path=mount_point,
                writable=True,
                comment='Default backup share created by SimpleSaferServer setup',
                valid_users=[admin_username]
            )
            logger.info(f"Created new backup share at {mount_point}")
        
        # Enable SMB services to start on boot
        try:
            subprocess.run(['systemctl', 'enable', 'smbd'], check=True)
            subprocess.run(['systemctl', 'enable', 'nmbd'], check=True)
            logger.info("SMB services enabled for boot")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to enable SMB services: {e}")
            # Don't fail setup for this, just log it
        
        logger.info(f"SMB share setup completed successfully. Share 'backup' created at {mount_point}")
        return True, None
        
    except Exception as e:
        logger.error(f"Error setting up SMB share: {e}")
        return False, str(e)

@setup.route('/api/setup/complete', methods=['POST'])
@setup_api_access_required
def complete_setup():
    """Complete the setup process"""
    try:
        # Get current config
        current_config = config_manager.get_all_config()
        logger.info(f"Current config during setup completion: {current_config}")

        # Validate required fields
        required_fields = {
            'system': ['username', 'server_name'],
            'backup': ['mount_point', 'uuid', 'email_address'],
            'schedule': ['backup_cloud_time']
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
            return jsonify({
                'success': False,
                'error': 'Missing required fields',
                'details': missing_fields
            })

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
            return jsonify({'success': False, 'error': f'Failed to install systemd tasks: {err}'})

        # Set up SMB share
        ok, err = setup_smb_share(current_config)
        if not ok:
            return jsonify({'success': False, 'error': f'Failed to set up SMB share: {err}'})

        # Mark setup as complete AFTER all systemd tasks are installed
        config_manager.mark_setup_complete()
        config_manager.load_config()  # Ensure in-memory config is up to date

        logger.info("Setup completed successfully, systemd tasks installed, and SMB share configured.")
        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error completing setup: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Error completing setup: {str(e)}',
            'details': 'An unexpected error occurred. Please check the system logs for more information.'
        })

@setup.route('/api/setup/system', methods=['POST'])
@setup_api_access_required
def setup_system_info():
    """Save system-level info such as username and server name"""
    try:
        data = request.get_json()
        username = data.get('username')
        server_name = data.get('server_name')

        if not username or not server_name:
            return jsonify({'success': False, 'error': 'Username and server name are required'})

        config_manager.set_value('system', 'username', username)
        config_manager.set_value('system', 'server_name', server_name)
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error saving system info: {e}")
        return jsonify({'success': False, 'error': str(e)}) 

@setup.route('/api/setup/mega/connect', methods=['POST'])
@setup_api_access_required
def mega_connect():
    """Authenticate with MEGA and list folders using rclone."""
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password are required.'})
        # Obscure password using rclone
        result = subprocess.run(["rclone", "obscure", password], stdout=subprocess.PIPE, check=True, text=True)
        obscured_pw = result.stdout.strip()
        # Build temp rclone config
        config_text = f"""
[mega]
type = mega
user = {email}
pass = {obscured_pw}
"""
        with NamedTemporaryFile(delete=False, mode="w", prefix="rclone-", suffix=".conf") as config_file:
            config_file.write(config_text)
            config_path = config_file.name
        try:
            # List folders at root
            lsjson = subprocess.run([
                "rclone", "lsjson", "mega:/", "--config", config_path
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if lsjson.returncode != 0:
                return jsonify({'success': False, 'error': 'Failed to list MEGA folders. Check credentials.'})
            import json as pyjson
            items = pyjson.loads(lsjson.stdout)
            folders = [item['Name'] for item in items if item['IsDir']]
            return jsonify({'success': True, 'folders': folders})
        finally:
            os.remove(config_path)
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error connecting to MEGA: {str(e)}'})

@setup.route('/api/setup/mega/list_folders', methods=['POST'])
@setup_api_access_required
def mega_list_folders():
    """List folders at a given MEGA path using rclone."""
    try:
        data = request.get_json()
        path = data.get('path', '/')
        email = data.get('email')
        password = data.get('password')
        if not email or not password:
            return jsonify({'error': 'Email and password are required.'})
        result = subprocess.run(["rclone", "obscure", password], stdout=subprocess.PIPE, check=True, text=True)
        obscured_pw = result.stdout.strip()
        config_text = f"""
[mega]
type = mega
user = {email}
pass = {obscured_pw}
"""
        from tempfile import NamedTemporaryFile
        with NamedTemporaryFile(delete=False, mode="w", prefix="rclone-", suffix=".conf") as config_file:
            config_file.write(config_text)
            config_path = config_file.name
        try:
            lsjson = subprocess.run([
                "rclone", "lsjson", f"mega:{path}", "--config", config_path
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if lsjson.returncode != 0:
                return jsonify({'error': 'Failed to list MEGA folders. Check credentials or path.'})
            import json as pyjson
            items = pyjson.loads(lsjson.stdout)
            folders = [item['Name'] for item in items if item['IsDir']]
            # Compute parent path
            parent = '/'.join(path.rstrip('/').split('/')[:-1]) or '/'
            return jsonify({'folders': folders, 'path': path, 'parent': parent})
        finally:
            os.remove(config_path)
    except Exception as e:
        return jsonify({'error': f'Error listing MEGA folders: {str(e)}'})

@setup.route('/api/setup/mega/create_folder', methods=['POST'])
@setup_api_access_required
def mega_create_folder_picker():
    """Create a new folder at a given MEGA path using rclone."""
    try:
        data = request.get_json()
        folder_name = data.get('folder_name')
        path = data.get('path', '/')
        email = data.get('email')
        password = data.get('password')
        if not folder_name or not email or not password:
            return jsonify({'error': 'Folder name, email, and password are required.'})
        result = subprocess.run(["rclone", "obscure", password], stdout=subprocess.PIPE, check=True, text=True)
        obscured_pw = result.stdout.strip()
        config_text = f"""
[mega]
type = mega
user = {email}
pass = {obscured_pw}
"""
        from tempfile import NamedTemporaryFile
        with NamedTemporaryFile(delete=False, mode="w", prefix="rclone-", suffix=".conf") as config_file:
            config_file.write(config_text)
            config_path = config_file.name
        try:
            # Create folder at mega:{path}/{folder_name}
            full_path = f"{path.rstrip('/')}/{folder_name}" if path != '/' else f"/{folder_name}"
            mkdir = subprocess.run([
                "rclone", "mkdir", f"mega:{full_path}", "--config", config_path
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if mkdir.returncode != 0:
                return jsonify({'error': 'Failed to create folder on MEGA.'})
            return jsonify({'success': True})
        finally:
            os.remove(config_path)
    except Exception as e:
        return jsonify({'error': f'Error creating folder: {str(e)}'})

@setup.route('/api/setup/mega/save', methods=['POST'])
@setup_api_access_required
def mega_save():
    """Save MEGA config (obscured password, selected folder) securely and write rclone config."""
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        folder = data.get('folder')
        if not email or not password or not folder:
            return jsonify({'success': False, 'error': 'Email, password, and folder are required.'})
        result = subprocess.run(["rclone", "obscure", password], stdout=subprocess.PIPE, check=True, text=True)
        obscured_pw = result.stdout.strip()
        # Save to config/secrets (for demo, store in config_manager, but should use encrypted secrets in production)
        config_manager.set_value('backup', 'cloud_mode', 'mega')
        config_manager.set_value('backup', 'mega_email', email)
        config_manager.set_value('backup', 'mega_pass', obscured_pw)
        config_manager.set_value('backup', 'mega_folder', folder)
        # Set rclone_dir for backup script compatibility
        config_manager.set_value('backup', 'rclone_dir', f"mega:{folder}")
        # Write rclone config for MEGA
        mega_rclone_config = f"""[mega]\ntype = mega\nuser = {email}\npass = {obscured_pw}\n"""
        if not system_utils.setup_rclone(mega_rclone_config):
            return jsonify({'success': False, 'error': 'Failed to write rclone config for MEGA'})
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error saving MEGA config: {str(e)}'}) 
