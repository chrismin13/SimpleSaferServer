from flask import Blueprint, render_template, jsonify, request, redirect, session
from config_manager import ConfigManager
from system_utils import SystemUtils
from user_manager import UserManager
from smb_manager import SMBManager
import logging
import subprocess
import os
import re
import shutil
from datetime import datetime
from tempfile import NamedTemporaryFile
from pathlib import Path

setup = Blueprint('setup', __name__)
config_manager = ConfigManager()
system_utils = SystemUtils()
user_manager = UserManager()
smb_manager = SMBManager()
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
        # Get detailed drive information using lsblk
        lsblk_result = subprocess.run(['lsblk', '-f', '-o', 'NAME,FSTYPE,LABEL,SIZE,MODEL,MOUNTPOINT,TYPE'], 
                                    capture_output=True, text=True)
        
        if lsblk_result.returncode != 0:
            return jsonify({'success': False, 'error': 'Failed to list drives'})

        drives = []
        current_drive = None
        
        # Get system drive to exclude it
        root_mount = subprocess.run(['mount | grep "on / "'], shell=True, capture_output=True, text=True)
        system_drive = None
        if root_mount.returncode == 0:
            system_drive = root_mount.stdout.split()[0]
        
        for line in lsblk_result.stdout.splitlines()[1:]:  # Skip header
            parts = line.split()
            if not parts:
                continue
                
            name = parts[0]
            if name.startswith('├─') or name.startswith('└─'):
                # This is a partition
                if current_drive:
                    partition = {
                        'path': f"/dev/{name[2:]}",  # Remove the tree characters
                        'type': parts[1] if len(parts) > 1 else 'unknown',
                        'label': parts[2] if len(parts) > 2 else '',
                        'size': parts[3] if len(parts) > 3 else '',
                        'mountpoint': parts[4] if len(parts) > 4 else ''
                    }
                    current_drive['partitions'].append(partition)
            else:
                # This is a drive
                if current_drive:
                    # Only add if it's a physical drive and not the system drive
                    if current_drive['type'] in ['disk', 'usb'] and current_drive['path'] != system_drive:
                        drives.append(current_drive)
                
                # Get drive model and type using udevadm
                udev_result = subprocess.run(['udevadm', 'info', '--query=property', f"/dev/{name}"], 
                                          capture_output=True, text=True)
                model = 'Unknown Drive'
                drive_type = 'unknown'
                if udev_result.returncode == 0:
                    for line in udev_result.stdout.splitlines():
                        if line.startswith('ID_MODEL='):
                            model = line.split('=')[1].strip()
                        elif line.startswith('ID_TYPE='):
                            drive_type = line.split('=')[1].strip()
                
                current_drive = {
                    'path': f"/dev/{name}",
                    'model': model,
                    'size': parts[3] if len(parts) > 3 else '',
                    'type': drive_type,
                    'partitions': []
                }
        
        # Add the last drive if it's a physical drive
        if current_drive and current_drive['type'] in ['disk', 'usb'] and current_drive['path'] != system_drive:
            drives.append(current_drive)

        return jsonify({
            'success': True,
            'drives': drives
        })

    except Exception as e:
        logger.error(f"Error listing drives: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@setup.route('/api/setup/format', methods=['POST'])
def format_drive():
    """Format the selected drive"""
    try:
        data = request.get_json()
        drive = data.get('drive')
        
        if not drive:
            return jsonify({'success': False, 'error': 'No drive selected'})

        # Check if drive is mounted
        mount_check = subprocess.run(['mount'], capture_output=True, text=True)
        mounted_partitions = []
        
        # Find all mounted partitions for this drive
        for line in mount_check.stdout.splitlines():
            if drive in line:
                parts = line.split()
                if len(parts) >= 2:
                    device = parts[0]
                    mount_point = parts[2]
                    mounted_partitions.append({
                        'device': device,
                        'mount_point': mount_point
                    })

        if mounted_partitions:
            partition_info = '\n'.join([f"- {p['device']} at {p['mount_point']}" for p in mounted_partitions])
            return jsonify({
                'success': False, 
                'error': 'Drive has mounted partitions',
                'details': f'The following partitions are currently mounted:\n{partition_info}\n\nPlease unmount all partitions before formatting.',
                'can_unmount': True
            })

        # Create a single partition if none exists
        partition = f"{drive}1"
        if not os.path.exists(partition):
            # Create partition using fdisk
            fdisk_input = f"n\np\n1\n\n\nw\n"
            result = subprocess.run(['fdisk', drive], input=fdisk_input.encode(), capture_output=True)
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
    """Unmount the selected drive and clean up fstab entries related to SimpleSaferServer"""
    try:
        data = request.get_json()
        drive = data.get('drive')
        
        if not drive:
            return jsonify({'success': False, 'error': 'No drive selected'})

        # Check if drive is mounted
        mount_check = subprocess.run(['mount'], capture_output=True, text=True)
        mounted_partitions = []
        
        # Find all mounted partitions for this drive
        for line in mount_check.stdout.splitlines():
            if drive in line:
                parts = line.split()
                if len(parts) >= 2:
                    device = parts[0]
                    mount_point = parts[2]
                    mounted_partitions.append({
                        'device': device,
                        'mount_point': mount_point
                    })

        if not mounted_partitions:
            return jsonify({
                'success': False,
                'error': f'No mounted partitions found for {drive}',
                'details': 'The drive might not be mounted or might not have any partitions.'
            })

        # Try to unmount each partition
        failed_unmounts = []
        for partition in mounted_partitions:
            result = subprocess.run(['umount', partition['device']], capture_output=True, text=True)
            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else 'Unknown error occurred'
                failed_unmounts.append({
                    'device': partition['device'],
                    'error': error_msg
                })

        if failed_unmounts:
            error_details = '\n'.join([f"{f['device']}: {f['error']}" for f in failed_unmounts])
            return jsonify({
                'success': False,
                'error': 'Failed to unmount some partitions',
                'details': f'The following partitions could not be unmounted:\n{error_details}\n\nPlease ensure no applications are using these partitions.'
            })

        # Remove any fstab entries related to SimpleSaferServer
        try:
            with open('/etc/fstab', 'r') as fstab_file:
                lines = fstab_file.readlines()
            new_lines = [line for line in lines if 'SimpleSaferServer' not in line]
            with open('/etc/fstab', 'w') as fstab_file:
                fstab_file.writelines(new_lines)
        except Exception as e:
            logger.error(f"Error cleaning up fstab: {e}")
            return jsonify({
                'success': False,
                'error': f'Error cleaning up fstab: {e}',
                'details': 'Unmount succeeded, but failed to clean up /etc/fstab.'
            })

        return jsonify({
            'success': True,
            'message': f'Successfully unmounted {len(mounted_partitions)} partition(s)'
        })

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
        drive = data.get('drive')
        mount_point = data.get('mount_point', '/media/backup')
        auto_mount = data.get('auto_mount', True)
        
        if not drive:
            return jsonify({'success': False, 'error': 'No drive selected'})

        # Check if drive is already mounted
        mount_check = subprocess.run(['mount'], capture_output=True, text=True)
        if drive in mount_check.stdout:
            return jsonify({
                'success': False,
                'error': 'Drive is already mounted',
                'details': 'Please unmount the drive first if you want to change mount settings.'
            })

        # Create mount point if it doesn't exist
        os.makedirs(mount_point, exist_ok=True)

        # Mount the drive using ntfs-3g
        result = subprocess.run(['ntfs-3g', drive, mount_point, '-o', 'rw,uid=1000,gid=1000'], capture_output=True, text=True)
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else 'Unknown error occurred'
            return jsonify({
                'success': False,
                'error': f'Error mounting drive: {error_msg}',
                'details': 'Please ensure the drive is not in use and try again.'
            })

        # Get UUID of the partition
        uuid_result = subprocess.run(['blkid', '-s', 'UUID', '-o', 'value', drive], capture_output=True, text=True)
        if uuid_result.returncode != 0:
            return jsonify({
                'success': False,
                'error': 'Failed to get drive UUID',
                'details': 'Could not determine the drive UUID. Please try again.'
            })
        
        uuid = uuid_result.stdout.strip()

        # Get USB ID of the drive (if available)
        try:
            logger = logging.getLogger(__name__)
            usb_id = ""
            # Find sysfs path for the block device
            sys_block_path = f"/sys/class/block/{os.path.basename(drive)}/device"
            parent = os.path.realpath(sys_block_path)
            logger.info(f"Starting sysfs walk for USB ID from: {parent}")
            while parent != "/":
                id_vendor_path = os.path.join(parent, "idVendor")
                id_product_path = os.path.join(parent, "idProduct")
                if os.path.isfile(id_vendor_path) and os.path.isfile(id_product_path):
                    with open(id_vendor_path) as f:
                        vendor = f.read().strip()
                    with open(id_product_path) as f:
                        product = f.read().strip()
                    usb_id = f"{vendor}:{product}"
                    logger.info(f"Found USB ID at {parent}: {usb_id}")
                    break
                parent = os.path.dirname(parent)
            if not usb_id:
                logger.info("USB ID not found, likely not a USB device or not detected.")
        except Exception as e:
            logger.error(f"Error getting USB ID: {e}")
            usb_id = ""

        # Add to fstab if auto_mount is enabled
        if auto_mount:
            fstab_entry = f"UUID={uuid}\t\t{mount_point}\tntfs-3g\tdefaults,nofail\t0\t0 # SimpleSaferServer\n"
            with open('/etc/fstab', 'a') as f:
                f.write(fstab_entry)

        # Save to config using ConfigManager
        config_manager.set_value('backup', 'mount_point', mount_point)
        config_manager.set_value('backup', 'uuid', uuid)
        config_manager.set_value('backup', 'usb_id', usb_id)  # Empty string means not a USB device or not detected
        
        # Verify the config was saved
        current_config = config_manager.get_all_config()
        logger.info(f"Current config after mounting: {current_config}")

        return jsonify({
            'success': True,
            'message': f'Successfully mounted {drive} at {mount_point}'
        })

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
        smtp_server = data.get('smtpServer')
        smtp_port = data.get('smtpPort')
        smtp_username = data.get('smtpUsername')
        smtp_password = data.get('smtpPassword')
        
        if not all([email, smtp_server, smtp_port, smtp_username, smtp_password]):
            logger.error("Missing email fields")
            return jsonify({'success': False, 'error': 'All email fields are required'})
        
        # Save email to config and write /etc/msmtprc
        config_manager.set_value('backup', 'email_address', email)

        if not system_utils.write_msmtp_config(email, smtp_server, smtp_port, smtp_username, smtp_password):
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
            'message': 'Schedule saved successfully'
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
        
        # Get the admin user's password from the user manager
        admin_user = user_manager.users.get(admin_username)
        if not admin_user:
            return False, f"Admin user {admin_username} not found in user database"
        
        # Ensure admin user exists in Samba
        if not user_manager.user_exists_in_samba(admin_username):
            # We need to recreate the user in Samba with their password
            # For now, we'll use a default password and let the user change it later
            # In a real implementation, you might want to store the password temporarily
            logger.warning(f"Admin user {admin_username} not found in Samba, creating with default password")
            
            # First ensure the user exists in the system
            try:
                subprocess.run(['id', admin_username], check=True, capture_output=True)
            except subprocess.CalledProcessError:
                # User doesn't exist, create them
                logger.info(f"Creating system user {admin_username}")
                subprocess.run(['sudo', 'useradd', '-m', '-s', '/bin/bash', admin_username], check=True)
            
            # Use the actual admin password from the user database
            admin_password = admin_user.get('password', 'admin')  # fallback to 'admin' if not found
            subprocess.run(['sudo', 'smbpasswd', '-s', '-a', admin_username], 
                         input=f"{admin_password}\n{admin_password}\n", text=True, check=True)
        
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