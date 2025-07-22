import subprocess
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

class SMBManager:
    def __init__(self):
        self.smb_conf_path = '/etc/samba/smb.conf'
        self.backup_dir = '/etc/samba/backups'
        
        # Ensure backup directory exists
        Path(self.backup_dir).mkdir(parents=True, exist_ok=True)

    def _create_backup(self):
        """Create a backup of the current smb.conf"""
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        backup_path = f'{self.backup_dir}/smb.conf.backup.{timestamp}'
        subprocess.run(['sudo', 'cp', self.smb_conf_path, backup_path], check=True)
        logger.info(f"Created backup of smb.conf at {backup_path}")
        return backup_path

    def _read_smb_conf(self):
        """Read the current smb.conf file"""
        try:
            with open(self.smb_conf_path, 'r') as f:
                return f.read()
        except FileNotFoundError:
            return self._get_default_config()

    def _get_default_config(self):
        """Get default SMB configuration"""
        return """#
# Sample configuration file for the Samba suite for Debian GNU/Linux.
#
# This is the main Samba configuration file. You should read the
# smb.conf(5) manual page in order to understand the options listed
# here. Samba has a huge number of configurable options most of which 
# are not shown in this example
#
# Some options that are often worth tuning have been included as
# commented-out examples in this file.
#  - When such options are commented with ";", the proposed setting
#    differs from the default Samba behaviour
#  - When commented with "#", the proposed setting is the default
#    behaviour of Samba but the option is considered important
#    enough to be mentioned here
#
# NOTE: Whenever you modify this file you should run the command
# "testparm" to check that you have not made any basic syntactic 
# errors. 

#======================= Global Settings =======================

[global]

## Browsing/Identification ###

# Change this to the workgroup/NT-domain name your Samba server will part of
   workgroup = WORKGROUP

#### Networking ####

# The specific set of interfaces / networks to bind to
# This can be either the interface name or an IP address/netmask;
# interface names are normally preferred
;   interfaces = 127.0.0.0/8 eth0

# Only bind to the named interfaces and/or networks; you must use the
# 'interfaces' option above to use this.
# It is recommended that you enable this feature if your Samba machine is
# not protected by a firewall or is a firewall itself.  However, this
# option cannot handle dynamic or non-broadcast interfaces correctly.
;   bind interfaces only = yes

#### Debugging/Accounting ####

# This tells Samba to use a separate log file for each machine
# that connects
   log file = /var/log/samba/log.%m

# Cap the size of the individual log files (in KiB).
   max log size = 1000

# We want Samba to only log to /var/log/samba/log.{smbd,nmbd}.
# Append syslog@1 if you want important messages to be sent to syslog too.
   logging = file

# Do something sensible when Samba crashes: mail the admin a backtrace
   panic action = /usr/share/samba/panic-action %d

####### Authentication #######

# Server role. Defines in which mode Samba will operate. Possible
# values are "standalone server", "member server", "classic primary
# domain controller", "classic backup domain controller", "active
# directory domain controller". 
#
# Most people will want "standalone server" or "member server".
# Running as "active directory domain controller" will require first
# running "samba-tool domain provision" to wipe databases and create a
# new domain.
   server role = standalone server

   obey pam restrictions = yes

# This boolean parameter controls whether Samba attempts to sync the Unix
# password with the SMB password when the encrypted SMB password in the
# passdb is changed.
   unix password sync = yes

# For Unix password sync to work on a Debian GNU/Linux system, the following
# parameters must be set (thanks to Ian Kahan <<kahan@informatik.tu-muenchen.de> for
# sending the correct chat script for the passwd program in Debian Sarge).
   passwd program = /usr/bin/passwd %u
   passwd chat = *Enter\\snew\\s*\\spassword:* %n\\n *Retype\\snew\\s*\\spassword:* %n\\n *password\\supdated\\ssuccessfully* .

# This boolean controls whether PAM will be used for password changes
# when requested by an SMB client instead of the program listed in
# 'passwd program'. The default is 'no'.
   pam password change = yes

# This option controls how unsuccessful authentication attempts are mapped
# to anonymous connections
   map to guest = never

########## Domains ###########

#
# The following settings only takes effect if 'server role = classic
# primary domain controller', 'server role = classic backup domain controller'
# or 'domain logons' is set 
#

# It specifies the location of the user's
# profile directory from the client point of view) The following
# required a [profiles] share to be setup on the samba server (see
# below)
;   logon path = \\\\%N\\profiles\\%U
# Another common choice is storing the profile in the user's home directory
# (this is Samba's default)
#   logon path = \\\\%N\\%U\\profile

# The following setting only takes effect if 'domain logons' is set
# It specifies the location of a user's home directory (from the client
# point of view)
;   logon drive = H:
#   logon home = \\\\%N\\%U

# The following setting only takes effect if 'domain logons' is set
# It specifies the script to run during logon. The script must be stored
# in the [netlogon] share
# NOTE: Must be store in 'DOS' file format convention
;   logon script = logon.cmd

# This allows Unix users to be created on the domain controller via the SAMR
# RPC pipe.  The example command creates a user account with a disabled Unix
# password; please adapt to your needs
; add user script = /usr/sbin/useradd --create-home %u

# This allows machine accounts to be created on the domain controller via the 
# SAMR RPC pipe.  
# The following assumes a "machines" group exists on the system
; add machine script  = /usr/sbin/useradd -g machines -c "%u machine account" -d /var/lib/samba -s /bin/false %u

# This allows Unix groups to be created on the domain controller via the SAMR
# RPC pipe.  
; add group script = /usr/sbin/addgroup --force-badname %g

############ Misc ############

# Using the following line enables you to customise your configuration
# on a per machine basis. The %m gets replaced with the netbios name
# of the machine that is connecting
;   include = /home/samba/etc/smb.conf.%m

# Some defaults for winbind (make sure you're not using the ranges
# for something else.)
;   idmap config * :              backend = tdb
;   idmap config * :              range   = 3000-7999
;   idmap config YOURDOMAINHERE : backend = tdb
;   idmap config YOURDOMAINHERE : range   = 100000-999999
;   template shell = /bin/bash

# Setup usershare options to enable non-root users to share folders
# with the net usershare command.

# Maximum number of usershare. 0 means that usershare is disabled.
#   usershare max shares = 100

# Allow users who've been granted usershare privileges to create
# public shares, not just authenticated ones
   usershare allow guests = yes

#======================= Share Definitions =======================

[homes]
   comment = Home Directories
   browseable = no

# By default, the home directories are exported read-only. Change the
# next parameter to 'no' if you want to be able to write to them.
   read only = yes

# File creation mask is set to 0700 for security reasons. If you want to
# create files with group=rw permissions, set next parameter to 0775.
   create mask = 0700

# Directory creation mask is set to 0700 for security reasons. If you want to
# create dirs. with group=rw permissions, set next parameter to 0775.
   directory mask = 0700

# By default, \\\\server\\username shares can be connected to by anyone
# with access to the samba server.
# The following parameter makes sure that only "username" can connect
# to \\\\server\\username
# This might need tweaking when using external authentication schemes
   valid users = %S

[printers]
   comment = All Printers
   browseable = no
   path = /var/tmp
   printable = yes
   guest ok = no
   read only = yes
   create mask = 0700

# Windows clients look for this share name as a source of downloadable
# printer drivers
[print$]
   comment = Printer Drivers
   path = /var/lib/samba/printers
   browseable = yes
   read only = yes
   guest ok = no
"""

    def _write_smb_conf(self, content):
        """Write content to smb.conf"""
        # Create backup first
        self._create_backup()
        
        # Write new configuration
        with open(self.smb_conf_path, 'w') as f:
            f.write(content)
        
        # Set proper permissions
        os.chmod(self.smb_conf_path, 0o644)

    def _restart_services(self):
        """Restart SMB services"""
        try:
            subprocess.run(['sudo', 'systemctl', 'restart', 'smbd'], check=True)
            subprocess.run(['sudo', 'systemctl', 'restart', 'nmbd'], check=True)
            logger.info("SMB services restarted successfully")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to restart SMB services: {e}")
            return False

    def get_shares(self):
        """Get all shares from smb.conf"""
        try:
            content = self._read_smb_conf()
            shares = []
            lines = content.split('\n')
            current_share = None
            
            for line in lines:
                line = line.strip()
                
                # Check for share section headers [share_name]
                if line.startswith('[') and line.endswith(']') and not line.startswith('[global]'):
                    share_name = line[1:-1]  # Remove brackets
                    # Exclude system shares
                    if share_name not in ['homes', 'printers', 'print$']:
                        current_share = {
                            'name': share_name, 
                            'path': '', 
                            'writable': False, 
                            'public': False, 
                            'comment': '',
                            'valid_users': []
                        }
                        shares.append(current_share)
                elif current_share and line and not line.startswith('#'):
                    # Parse share configuration
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        if key == 'path':
                            current_share['path'] = value
                        elif key == 'writeable' or key == 'writable':
                            current_share['writable'] = value.lower() in ['yes', 'true', '1']
                        elif key == 'public':
                            current_share['public'] = value.lower() in ['yes', 'true', '1']
                        elif key == 'comment':
                            current_share['comment'] = value.strip('"')
                        elif key == 'valid users':
                            # Parse valid users list
                            users = value.split()
                            current_share['valid_users'] = [u for u in users if u != '%S']
            
            return shares
        except Exception as e:
            logger.error(f"Error reading SMB shares: {e}")
            return []

    def add_share(self, name, path, writable=True, comment="", valid_users=None):
        """Add a new share"""
        try:
            # Validation
            if not name or not path:
                raise ValueError("Share name and path are required")
            
            # Check if path exists
            if not os.path.exists(path):
                raise ValueError(f"Path {path} does not exist")
            
            # Check if share already exists
            existing_shares = self.get_shares()
            if any(share['name'] == name for share in existing_shares):
                raise ValueError(f"Share {name} already exists")
            
            # Read current configuration
            content = self._read_smb_conf()
            
            # Add share configuration
            share_config = f"""
[{name}]
   path = {path}
   writeable = {'Yes' if writable else 'No'}
   create mask = 0777
   directory mask = 0777
   public = no
   comment = {comment}
"""
            
            # Add valid users if specified
            if valid_users:
                users_str = ' '.join(valid_users)
                share_config += f"   valid users = {users_str}\n"
            
            # Append to end of file
            content += share_config
            
            # Write updated configuration
            self._write_smb_conf(content)
            
            # Restart services
            if not self._restart_services():
                raise Exception("Failed to restart SMB services")
            
            return True
        except Exception as e:
            logger.error(f"Error adding SMB share: {e}")
            raise

    def update_share(self, old_name, new_name, path, writable=True, comment="", valid_users=None):
        """Update an existing share"""
        try:
            # Validation
            if not new_name or not path:
                raise ValueError("Share name and path are required")
            
            # Check if path exists
            if not os.path.exists(path):
                raise ValueError(f"Path {path} does not exist")
            
            # Check if new name conflicts with existing shares
            existing_shares = self.get_shares()
            if any(share['name'] == new_name and share['name'] != old_name for share in existing_shares):
                raise ValueError(f"Share {new_name} already exists")
            
            # Read current configuration
            content = self._read_smb_conf()
            lines = content.split('\n')
            
            # Find and replace the share section
            new_lines = []
            in_share_section = False
            share_found = False
            
            for line in lines:
                if f'[{old_name}]' in line:
                    in_share_section = True
                    share_found = True
                    # Add new share configuration
                    new_lines.append(f"[{new_name}]")
                    new_lines.append(f"   path = {path}")
                    new_lines.append(f"   writeable = {'Yes' if writable else 'No'}")
                    new_lines.append(f"   create mask = 0777")
                    new_lines.append(f"   directory mask = 0777")
                    new_lines.append(f"   public = no")
                    new_lines.append(f"   comment = {comment}")
                    
                    # Add valid users if specified
                    if valid_users:
                        users_str = ' '.join(valid_users)
                        new_lines.append(f"   valid users = {users_str}")
                    
                    new_lines.append("")
                elif in_share_section and line.strip() and not line.startswith('   '):
                    # End of share section
                    in_share_section = False
                    new_lines.append(line)
                elif not in_share_section:
                    new_lines.append(line)
            
            if not share_found:
                raise ValueError(f"Share {old_name} not found")
            
            # Write updated configuration
            self._write_smb_conf('\n'.join(new_lines))
            
            # Restart services
            if not self._restart_services():
                raise Exception("Failed to restart SMB services")
            
            return True
        except Exception as e:
            logger.error(f"Error updating SMB share: {e}")
            raise

    def delete_share(self, name):
        """Delete a share"""
        try:
            # Read current configuration
            content = self._read_smb_conf()
            lines = content.split('\n')
            
            # Remove the share section
            new_lines = []
            in_share_section = False
            share_found = False
            
            for line in lines:
                if f'[{name}]' in line:
                    in_share_section = True
                    share_found = True
                    continue  # Skip this line
                elif in_share_section and line.strip() and not line.startswith('   '):
                    # End of share section
                    in_share_section = False
                    new_lines.append(line)
                elif not in_share_section:
                    new_lines.append(line)
            
            if not share_found:
                raise ValueError(f"Share {name} not found")
            
            # Write updated configuration
            self._write_smb_conf('\n'.join(new_lines))
            
            # Restart services
            if not self._restart_services():
                raise Exception("Failed to restart SMB services")
            
            return True
        except Exception as e:
            logger.error(f"Error deleting SMB share: {e}")
            raise

    def get_share_users(self, share_name):
        """Get users who have access to a specific share"""
        try:
            shares = self.get_shares()
            for share in shares:
                if share['name'] == share_name:
                    return share.get('valid_users', [])
            return []
        except Exception as e:
            logger.error(f"Error getting share users: {e}")
            return []

    def update_share_users(self, share_name, users):
        """Update the list of users who have access to a share"""
        try:
            shares = self.get_shares()
            share = None
            
            for s in shares:
                if s['name'] == share_name:
                    share = s
                    break
            
            if not share:
                raise ValueError(f"Share {share_name} not found")
            
            # Update the share with new user list
            return self.update_share(
                share_name, 
                share_name, 
                share['path'], 
                share['writable'], 
                share['comment'], 
                users
            )
        except Exception as e:
            logger.error(f"Error updating share users: {e}")
            raise

    def get_service_status(self):
        """Get SMB service status"""
        try:
            smbd_result = subprocess.run(['systemctl', 'is-active', 'smbd'], 
                                       capture_output=True, text=True)
            nmbd_result = subprocess.run(['systemctl', 'is-active', 'nmbd'], 
                                       capture_output=True, text=True)
            
            return {
                'smbd': smbd_result.stdout.strip(),
                'nmbd': nmbd_result.stdout.strip()
            }
        except Exception as e:
            logger.error(f"Error getting service status: {e}")
            return {'smbd': 'error', 'nmbd': 'error'} 