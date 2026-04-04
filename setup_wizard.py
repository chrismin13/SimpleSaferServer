from flask import Blueprint, render_template, jsonify, request, redirect, session
from backup_drive_setup import (
    BackupDriveSetupError,
    apply_backup_drive_configuration,
    list_available_drives as get_available_backup_drives,
    _get_mounted_partitions_for_disk,
    unmount_disk_partitions,
    unmount_selected_partition,
)
from config_manager import ConfigManager
from system_utils import SystemUtils
from user_manager import UserManager
from smb_manager import SMBManager
import logging
import subprocess
import os
import re
from datetime import datetime
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

@setup.route('/api/setup/drives', methods=['GET'])
def list_drives():
    """List available drives with detailed information"""
    try:
        drives = get_available_backup_drives(runtime=runtime, ntfs_only=False)
        return jsonify({'success': True, 'drives': drives})
    except Exception as e:
        logger.error(f"Error listing drives: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@setup.route('/api/setup/format', methods=['POST'])
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

        mounted_partitions = _get_mounted_partitions_for_disk(disk)

        if mounted_partitions:
            partition_info = '\n'.join([f"- {p['device']} at {p['mount_point']}" for p in mounted_partitions])
            return jsonify({
                'success': False, 
                'error': 'Drive has mounted partitions',
                'details': f'The following partitions are currently mounted:\n{partition_info}\n\nPlease unmount all partitions before formatting.',
                'can_unmount': True
            })

        # Create a single partition if none exists
        partition = f"{disk}1"
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
def unmount_drive():
    """Unmount the selected drive"""
    try:
        data = request.get_json()
        # The setup wizard uses this route for two different UI controls:
        # whole-disk unmount before formatting, and exact-partition unmount
        # before mounting an NTFS partition in step 3.
        disk = data.get('disk')
        partition = data.get('partition')
        if disk:
            message = unmount_disk_partitions(disk, runtime=runtime)
        else:
            message = unmount_selected_partition(partition, runtime=runtime)
        return jsonify({'success': True, 'message': message})
    except BackupDriveSetupError as e:
        return jsonify({'success': False, 'error': str(e)})
    except Exception as e:
        logger.error(f"Error unmounting drive: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Error unmounting drive: {str(e)}',
            'details': 'An unexpected error occurred. Please check the system logs for more information.'
        })

@setup.route('/api/setup/mount', methods=['POST'])
def mount_drive():
    """Mount the selected drive"""
    try:
        data = request.get_json()
        # Step 3 always selects a filesystem-bearing partition, never a whole
        # disk. That aligns it with the rerun flow on Drive Health.
        partition = data.get('partition')
        mount_point = data.get('mount_point') or (runtime.default_mount_point if runtime.is_fake else '/media/backup')
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
        return jsonify({'success': False, 'error': str(e)})
    except Exception as e:
        logger.error(f"Error mounting drive: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Error mounting drive: {str(e)}',
            'details': 'An unexpected error occurred. Please check the system logs for more information.'
        })

@setup.route('/api/setup/rclone', methods=['POST'])
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
        mount_point = backup.get('mount_point', '/media/backup')
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
