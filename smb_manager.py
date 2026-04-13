import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from runtime import get_fake_state, get_runtime

logger = logging.getLogger(__name__)

SMB_DOCS_URL = (
    "https://github.com/chrismin13/SimpleSaferServer/blob/main/docs/network_file_sharing.md"
    "#manual-conversion-unmanaged-share-to-simplesaferserver-managed-share"
)
MANAGED_SHARE_BEGIN_PREFIX = "# BEGIN SimpleSaferServer share: "
MANAGED_SHARE_END_PREFIX = "# END SimpleSaferServer share: "
SYSTEM_SHARE_NAMES = {"global", "homes", "printers", "print$"}
VALID_SHARE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


class SMBConfigError(ValueError):
    """Raised when smb.conf contains ownership markers that SimpleSaferServer cannot trust."""


@dataclass
class ParsedShare:
    name: str
    managed: bool
    path: str = ""
    writable: bool = False
    public: bool = False
    comment: str = ""
    valid_users: List[str] = field(default_factory=list)
    start_line: int = 0
    end_line: int = 0
    raw_text: str = ""

    def as_dict(self):
        return {
            "name": self.name,
            "path": self.path,
            "writable": self.writable,
            "public": self.public,
            "comment": self.comment,
            "valid_users": list(self.valid_users),
            "managed": self.managed,
        }


def _extract_section_name(line: str) -> Optional[str]:
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]") and len(stripped) > 2:
        return stripped[1:-1].strip()
    return None


def _contains_control_characters(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


class SMBManager:
    def __init__(self, runtime=None):
        self.runtime = runtime or get_runtime()
        self.smb_conf_path = str(self.runtime.samba_dir / "smb.conf")
        self.backup_dir = str(self.runtime.samba_backup_dir)
        self.fake_state = get_fake_state() if self.runtime.is_fake else None

        # The backup directory is intentionally outside smb.conf itself so a
        # parse failure never prevents us from preserving the last good file.
        Path(self.backup_dir).mkdir(parents=True, exist_ok=True)

    def _create_backup(self):
        """Create a backup of the current smb.conf."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_path = f"{self.backup_dir}/smb.conf.backup.{timestamp}"
        if self.runtime.is_fake:
            Path(backup_path).write_text(self._read_smb_conf())
        else:
            subprocess.run(["sudo", "cp", self.smb_conf_path, backup_path], check=True)
        logger.info("Created backup of smb.conf at %s", backup_path)
        return backup_path

    def _read_smb_conf(self):
        """Read the current smb.conf file."""
        try:
            with open(self.smb_conf_path, "r") as handle:
                return handle.read()
        except FileNotFoundError:
            return self._get_default_config()

    def _get_default_config(self):
        """Get default SMB configuration."""
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
        """Write content to smb.conf."""
        self._create_backup()
        with open(self.smb_conf_path, "w") as handle:
            handle.write(content)
        os.chmod(self.smb_conf_path, 0o644)

    def _validate_smb_conf_candidate(self, candidate_path: Path):
        validator = shutil.which("testparm")
        if validator:
            command = [validator, "-s", str(candidate_path)]
        else:
            validator = shutil.which("smbd")
            if not validator:
                raise RuntimeError(
                    "Could not validate smb.conf because neither 'testparm' nor 'smbd' is available."
                )
            command = [validator, "-t", "-s", str(candidate_path)]

        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            details = result.stderr.strip() or result.stdout.strip() or "unknown validation error"
            raise SMBConfigError(f"Samba configuration validation failed: {details}")

    def _restore_smb_conf_backup(self, backup_path: Path):
        shutil.copy2(backup_path, self.smb_conf_path)
        os.chmod(self.smb_conf_path, 0o644)

    def _commit_smb_conf(self, content: str):
        if self.runtime.is_fake:
            self._write_smb_conf(content)
            if not self._restart_services():
                raise Exception("Failed to restart SMB services")
            return

        live_path = Path(self.smb_conf_path)
        backup_path = Path(self._create_backup())
        temp_path = None
        replaced_live_config = False

        try:
            with tempfile.NamedTemporaryFile(
                "w",
                delete=False,
                dir=str(live_path.parent),
                prefix=f"{live_path.name}.",
                suffix=".tmp",
            ) as handle:
                handle.write(content)
                temp_path = Path(handle.name)

            os.chmod(temp_path, 0o644)
            # Validate the candidate before replacing the live file so Samba is
            # never pointed at a config we already know is broken.
            self._validate_smb_conf_candidate(temp_path)
            os.replace(temp_path, live_path)
            replaced_live_config = True
            temp_path = None

            if not self._restart_services():
                raise RuntimeError("Failed to restart SMB services")
        except Exception as original_error:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

            if replaced_live_config:
                try:
                    self._restore_smb_conf_backup(backup_path)
                    self._restart_services()
                except Exception as rollback_error:
                    logger.error(
                        "Failed to restore smb.conf after SMB update error: %s",
                        rollback_error,
                    )

            raise original_error

    def _restart_services(self):
        """Restart SMB services."""
        if self.runtime.is_fake:
            self.fake_state.set_smb_services("active", "active")
            logger.info("Fake mode: marked SMB services as active")
            return True
        try:
            subprocess.run(["sudo", "systemctl", "restart", "smbd"], check=True)
            subprocess.run(["sudo", "systemctl", "restart", "nmbd"], check=True)
            logger.info("SMB services restarted successfully")
            return True
        except subprocess.CalledProcessError as exc:
            logger.error("Failed to restart SMB services: %s", exc)
            return False

    def _parse_share_block(self, block_lines, *, managed, marker_name=None):
        share_name = None
        share_data = {
            "path": "",
            "writable": False,
            "public": False,
            "comment": "",
            "valid_users": [],
        }

        for raw_line in block_lines:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith(";"):
                continue

            section_name = _extract_section_name(stripped)
            if section_name is not None:
                if share_name is not None:
                    raise SMBConfigError(
                        "SimpleSaferServer only supports one share section per managed block."
                    )
                share_name = section_name
                continue

            if share_name is None:
                continue

            if "=" not in stripped:
                continue

            key, value = stripped.split("=", 1)
            key = key.strip().lower()
            value = value.strip()

            if key in {"writeable", "writable"}:
                share_data["writable"] = value.lower() in {"yes", "true", "1"}
            elif key == "public":
                share_data["public"] = value.lower() in {"yes", "true", "1"}
            elif key == "path":
                share_data["path"] = value
            elif key == "comment":
                share_data["comment"] = value.strip('"')
            elif key == "valid users":
                share_data["valid_users"] = [user for user in value.split() if user != "%S"]

        if share_name is None:
            raise SMBConfigError("Failed to find a Samba share section inside a managed block.")

        if marker_name is not None and share_name != marker_name:
            raise SMBConfigError(
                "Managed share markers do not match the enclosed share name for '{}'.".format(marker_name)
            )

        return ParsedShare(name=share_name, managed=managed, **share_data)

    def _parse_smb_conf(self, content: str) -> Tuple[List[str], List[ParsedShare]]:
        lines = content.splitlines(keepends=True)
        shares = []
        index = 0

        while index < len(lines):
            stripped = lines[index].strip()

            if stripped.startswith(MANAGED_SHARE_BEGIN_PREFIX):
                marker_name = stripped[len(MANAGED_SHARE_BEGIN_PREFIX):].strip()
                if not marker_name:
                    raise SMBConfigError("Managed share marker is missing a share name.")

                start_line = index
                index += 1

                while index < len(lines):
                    end_line = lines[index].strip()
                    if end_line.startswith(MANAGED_SHARE_BEGIN_PREFIX):
                        raise SMBConfigError(
                            "Nested SimpleSaferServer share markers were found in smb.conf."
                        )
                    if end_line == f"{MANAGED_SHARE_END_PREFIX}{marker_name}":
                        break
                    index += 1

                if index >= len(lines):
                    raise SMBConfigError(
                        "Managed share '{}' is missing its END marker in smb.conf.".format(marker_name)
                    )

                block_end = index + 1
                share = self._parse_share_block(
                    lines[start_line + 1:index],
                    managed=True,
                    marker_name=marker_name,
                )
                share.start_line = start_line
                share.end_line = block_end
                share.raw_text = "".join(lines[start_line:block_end])
                shares.append(share)
                index = block_end
                continue

            section_name = _extract_section_name(stripped)
            if section_name and section_name.lower() not in SYSTEM_SHARE_NAMES:
                start_line = index
                index += 1

                while index < len(lines):
                    current = lines[index].strip()
                    if current.startswith(MANAGED_SHARE_BEGIN_PREFIX):
                        break
                    if _extract_section_name(current) is not None:
                        break
                    index += 1

                share = self._parse_share_block(lines[start_line:index], managed=False)
                share.start_line = start_line
                share.end_line = index
                share.raw_text = "".join(lines[start_line:index])
                shares.append(share)
                continue

            index += 1

        return lines, shares

    def _load_shares(self):
        return self._parse_smb_conf(self._read_smb_conf())

    def _find_share_record(self, shares, name, *, managed=None):
        matches = [
            share for share in shares
            if share.name == name and (managed is None or share.managed == managed)
        ]
        if len(matches) > 1:
            raise SMBConfigError(
                "Multiple Samba shares named '{}' were found, so SimpleSaferServer cannot act safely. "
                "See {} for manual cleanup guidance.".format(name, SMB_DOCS_URL)
            )
        return matches[0] if matches else None

    def _validate_share_input(self, name, path):
        if not name or not path:
            raise ValueError("Share name and path are required")
        if not isinstance(name, str) or _contains_control_characters(name) or not VALID_SHARE_NAME_RE.fullmatch(name):
            raise ValueError(
                "Share name may only contain letters, numbers, hyphens, and underscores."
            )
        if not isinstance(path, str) or _contains_control_characters(path):
            raise ValueError("Share path contains unsupported control characters.")
        if not os.path.isdir(path):
            raise ValueError(f"Path {path} must be an existing directory")

    def _validate_renderable_share_field(self, field_name, value):
        if not isinstance(value, str):
            raise ValueError(f"{field_name} must be a string.")
        if _contains_control_characters(value):
            raise ValueError(f"{field_name} contains unsupported control characters.")
        return value

    def _validate_valid_users(self, valid_users):
        if valid_users is None:
            return []
        if isinstance(valid_users, (str, bytes)):
            raise ValueError("valid_users must be a sequence of usernames, not a string")

        validated_users = []
        for username in valid_users:
            if not isinstance(username, str):
                raise ValueError("Share usernames must be strings.")
            if _contains_control_characters(username) or not VALID_SHARE_NAME_RE.fullmatch(username):
                raise ValueError(
                    "Share usernames may only contain letters, numbers, hyphens, and underscores."
                )
            validated_users.append(username)
        return validated_users

    def _render_managed_share_block(self, name, path, writable=True, comment="", valid_users=None):
        name = self._validate_renderable_share_field("Share name", name)
        if not VALID_SHARE_NAME_RE.fullmatch(name):
            raise ValueError(
                "Share name may only contain letters, numbers, hyphens, and underscores."
            )

        path = self._validate_renderable_share_field("Share path", path)
        comment = self._validate_renderable_share_field("Share comment", comment)
        valid_users = self._validate_valid_users(valid_users or [])

        lines = [
            f"{MANAGED_SHARE_BEGIN_PREFIX}{name}\n",
            f"[{name}]\n",
            f"   path = {path}\n",
            f"   writeable = {'Yes' if writable else 'No'}\n",
            "   create mask = 0777\n",
            "   directory mask = 0777\n",
            "   public = no\n",
            f"   comment = {comment}\n",
        ]
        if valid_users:
            lines.append(f"   valid users = {' '.join(valid_users)}\n")
        lines.append(f"{MANAGED_SHARE_END_PREFIX}{name}\n")
        return lines

    def _append_managed_block(self, lines, block_lines):
        new_lines = list(lines)
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] = new_lines[-1] + "\n"
        if new_lines and new_lines[-1].strip():
            new_lines.append("\n")
        new_lines.extend(block_lines)
        return new_lines

    def list_managed_shares(self):
        _, shares = self._load_shares()
        return [share.as_dict() for share in shares if share.managed]

    def list_unmanaged_shares(self):
        _, shares = self._load_shares()
        return [share.as_dict() for share in shares if not share.managed]

    def get_managed_share(self, name):
        _, shares = self._load_shares()
        share = self._find_share_record(shares, name, managed=True)
        return share.as_dict() if share else None

    def create_managed_share(self, name, path, writable=True, comment="", valid_users=None):
        self._validate_share_input(name, path)

        lines, shares = self._load_shares()
        if self._find_share_record(shares, name) is not None:
            raise ValueError(
                "Share '{}' already exists. SimpleSaferServer will not overwrite an existing unmanaged "
                "share with the same name. See {} for manual conversion guidance.".format(name, SMB_DOCS_URL)
            )

        block_lines = self._render_managed_share_block(name, path, writable, comment, valid_users)
        new_lines = self._append_managed_block(lines, block_lines)
        self._commit_smb_conf("".join(new_lines))

        return True

    def update_managed_share(self, old_name, new_name, path, writable=True, comment="", valid_users=None):
        self._validate_share_input(new_name, path)

        lines, shares = self._load_shares()
        share = self._find_share_record(shares, old_name, managed=True)
        if share is None:
            if self._find_share_record(shares, old_name, managed=False) is not None:
                raise ValueError(
                    "Share '{}' is not managed by SimpleSaferServer, so it cannot be edited here. "
                    "See {} for manual conversion guidance.".format(old_name, SMB_DOCS_URL)
                )
            raise ValueError(f"Share {old_name} not found")

        conflict = self._find_share_record(shares, new_name)
        if conflict is not None and not (conflict.managed and conflict.name == old_name):
            raise ValueError(
                "Share '{}' already exists. SimpleSaferServer will not overwrite an unmanaged share "
                "with the same name. See {} for manual conversion guidance.".format(new_name, SMB_DOCS_URL)
            )

        new_lines = list(lines)
        replacement = self._render_managed_share_block(new_name, path, writable, comment, valid_users)
        new_lines[share.start_line:share.end_line] = replacement
        self._commit_smb_conf("".join(new_lines))

        return True

    def delete_managed_share(self, name):
        lines, shares = self._load_shares()
        share = self._find_share_record(shares, name, managed=True)
        if share is None:
            if self._find_share_record(shares, name, managed=False) is not None:
                raise ValueError(
                    "Share '{}' is not managed by SimpleSaferServer, so it cannot be deleted here. "
                    "See {} for manual conversion guidance.".format(name, SMB_DOCS_URL)
                )
            raise ValueError(f"Share {name} not found")

        new_lines = list(lines)
        del new_lines[share.start_line:share.end_line]
        self._commit_smb_conf("".join(new_lines))

        return True

    def ensure_default_backup_share(self, mount_point, admin_username, fake_mode_comment=None, comment=None):
        if comment is None and self.runtime.is_fake and fake_mode_comment is not None:
            comment = fake_mode_comment
        elif comment is None and self.runtime.is_fake:
            comment = "Fake-mode backup share"
        elif comment is None:
            comment = "Default backup share created by SimpleSaferServer setup"

        unmanaged_backup = self._find_share_record(self._load_shares()[1], "backup", managed=False)
        if unmanaged_backup is not None:
            raise ValueError(
                "An unmanaged Samba share named 'backup' already exists. SimpleSaferServer will not overwrite it. "
                "Convert it manually or remove it first. See {} for manual conversion guidance.".format(SMB_DOCS_URL)
            )

        managed_backup = self.get_managed_share("backup")
        if managed_backup is not None:
            return self.update_managed_share(
                "backup",
                "backup",
                mount_point,
                writable=True,
                comment=comment,
                valid_users=[admin_username],
            )

        return self.create_managed_share(
            "backup",
            mount_point,
            writable=True,
            comment=comment,
            valid_users=[admin_username],
        )

    # Compatibility wrappers for older call sites that still expect the old
    # names while the rest of the codebase is migrating to explicit ownership.
    def get_shares(self):
        return self.list_managed_shares()

    def add_share(self, name, path, writable=True, comment="", valid_users=None):
        return self.create_managed_share(name, path, writable, comment, valid_users)

    def update_share(self, old_name, new_name, path, writable=True, comment="", valid_users=None):
        return self.update_managed_share(old_name, new_name, path, writable, comment, valid_users)

    def delete_share(self, name):
        return self.delete_managed_share(name)

    def _get_managed_share_or_raise(self, share_name):
        # Keep the unmanaged-share rejection in one place so legacy helper
        # methods do not drift apart and accidentally expose raw Samba state.
        _, shares = self._load_shares()
        share = self._find_share_record(shares, share_name)
        if share is None:
            raise ValueError(f"Share {share_name} not found")
        if not share.managed:
            raise ValueError(
                "Share '{}' is not managed by SimpleSaferServer, so it cannot be edited here. "
                "See {} for manual conversion guidance.".format(share_name, SMB_DOCS_URL)
            )
        return self.get_managed_share(share_name)

    def get_share_users(self, share_name):
        # Callers use this to populate edit flows, so unmanaged shares need an
        # explicit error instead of looking like empty access lists.
        share = self._get_managed_share_or_raise(share_name)
        return share.get("valid_users", [])

    def update_share_users(self, share_name, users):
        share = self._get_managed_share_or_raise(share_name)
        return self.update_managed_share(
            share_name,
            share_name,
            share["path"],
            share["writable"],
            share["comment"],
            users,
        )

    def get_service_status(self):
        """Get SMB service status."""
        if self.runtime.is_fake:
            return self.fake_state.get_smb_services()
        try:
            smbd_result = subprocess.run(["systemctl", "is-active", "smbd"], capture_output=True, text=True)
            nmbd_result = subprocess.run(["systemctl", "is-active", "nmbd"], capture_output=True, text=True)
            return {
                "smbd": smbd_result.stdout.strip(),
                "nmbd": nmbd_result.stdout.strip(),
            }
        except Exception as exc:
            logger.error("Error getting service status: %s", exc)
            return {"smbd": "error", "nmbd": "error"}
