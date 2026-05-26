import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from simple_safer_server.adapters.command_runner import CalledProcessError
from simple_safer_server.adapters.smb_commands import SmbCommandAdapter
from simple_safer_server.services.runtime import get_fake_state, get_runtime
from simple_safer_server.services.samba_layout import (
    SSS_SHARES_FILENAME,
    SambaLayoutError,
    SambaLayoutService,
)

logger = logging.getLogger(__name__)

SMB_DOCS_URL = (
    "https://github.com/chrismin13/SimpleSaferServer/blob/main/docs/network_file_sharing.md"
    "#manual-conversion-unmanaged-share-to-simplesaferserver-managed-share"
)
SYSTEM_SHARE_NAMES = {"global", "homes", "printers", "print$"}
VALID_SHARE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


class SMBConfigError(ValueError):
    """Raised when Samba share configuration cannot be parsed or published safely."""


class SMBOperationError(RuntimeError):
    """Raised when a Samba operation fails after validation has already passed."""


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
    def __init__(self, runtime=None, command_adapter=None):
        self.runtime = runtime or get_runtime()
        self.command_adapter = command_adapter or SmbCommandAdapter()
        self.smb_conf_path = str(self.runtime.samba_dir / "smb.conf")
        self.sss_shares_path = self.runtime.samba_dir / SSS_SHARES_FILENAME
        self.fake_state = get_fake_state(self.runtime) if self.runtime.is_fake else None

    def _read_smb_conf(self):
        """Read the current smb.conf file."""
        try:
            with open(self.smb_conf_path, encoding="utf-8") as handle:
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

    def _ensure_layout_for_share_write(self):
        SambaLayoutService(
            runtime=self.runtime,
            command_adapter=self.command_adapter,
        ).ensure_layout()

    def _validate_effective_smb_config(self):
        validator = shutil.which("testparm") or shutil.which("smbd") or "testparm"
        result = self.command_adapter.validate_config(validator, Path(self.smb_conf_path))
        if result.returncode != 0:
            details = result.stderr.strip() or result.stdout.strip() or "unknown validation error"
            raise SMBConfigError(f"Samba configuration validation failed: {details}")

    def _strip_sss_include_blocks(self, content: str):
        layout = SambaLayoutService(runtime=self.runtime, command_adapter=self.command_adapter)
        try:
            return layout.strip_owned_include_blocks(content)
        except SambaLayoutError as exc:
            raise SMBConfigError(str(exc)) from exc

    def _inspect_unmanaged_effective_shares(self):
        candidate_path = None
        try:
            # Effective-config inspection intentionally uses volatile runtime
            # storage so routine write-safety checks do not touch durable media.
            self.runtime.volatile_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                delete=False,
                dir=str(self.runtime.volatile_dir),
                prefix="smb-unmanaged-candidate.",
                suffix=".conf",
                encoding="utf-8",
            ) as handle:
                handle.write(self._strip_sss_include_blocks(self._read_smb_conf()))
                candidate_path = Path(handle.name)
            os.chmod(str(candidate_path), 0o644)

            validator = shutil.which("testparm") or shutil.which("smbd") or "testparm"
            # Keep the inspection candidate on volatile storage, but run testparm
            # from Samba's config directory so relative admin includes keep the
            # same meaning they have when Samba reads smb.conf normally.
            result = self.command_adapter.validate_config(
                validator,
                candidate_path,
                cwd=self.runtime.samba_dir,
            )
            if result.returncode != 0:
                details = (
                    result.stderr.strip() or result.stdout.strip() or "unknown inspection error"
                )
                raise SMBConfigError(f"Could not inspect the effective Samba config: {details}")

            _, shares = self._parse_smb_conf(result.stdout)
            return shares
        except SMBConfigError:
            raise
        except Exception as exc:
            raise SMBConfigError(f"Could not inspect the effective Samba config: {exc}") from exc
        finally:
            if candidate_path is not None and candidate_path.exists():
                candidate_path.unlink()

    def _commit_sss_shares_file(self, content: str):
        # The shares include is the ownership boundary. Snapshot this file
        # separately so a bad publish never rewrites administrator-owned smb.conf.
        original_exists = self.sss_shares_path.exists()
        original_content = (
            self.sss_shares_path.read_text(encoding="utf-8") if original_exists else ""
        )
        original_mode = self.sss_shares_path.stat().st_mode & 0o777 if original_exists else 0o644

        try:
            self._write_sss_shares_file(content, 0o644)
            self._validate_effective_smb_config()
            if not self._restart_services():
                raise RuntimeError("Failed to restart SMB services")
        except Exception as publish_error:
            if original_exists:
                self._write_sss_shares_file(original_content, original_mode)
            elif self.sss_shares_path.exists():
                self.sss_shares_path.unlink()
            if not self._restart_required_smbd_after_rollback():
                raise SMBOperationError(
                    "Samba share update failed and rollback could not restart smbd. "
                    "Check systemd status and the Samba journal before retrying."
                ) from publish_error
            raise

    def _write_sss_shares_file(self, content: str, mode: int):
        temp_path = None
        try:
            self.sss_shares_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                delete=False,
                dir=str(self.sss_shares_path.parent),
                prefix=f"{self.sss_shares_path.name}.",
                suffix=".tmp",
                encoding="utf-8",
            ) as handle:
                handle.write(content)
                temp_path = Path(handle.name)
            os.chmod(str(temp_path), mode)
            if not self.runtime.is_fake:
                os.chown(str(temp_path), 0, 0)
            os.replace(str(temp_path), str(self.sss_shares_path))
            temp_path = None
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

    def _reload_or_restart_smbd(self) -> bool:
        """Apply new configuration to smbd gracefully, with a hard fallback restart.

        If smbd is active, we attempt to reload the config dynamically via smbcontrol
        so active TCP connections are not disrupted. If that fails, or if smbd is
        inactive, we fall back to a full systemd restart to ensure the daemon is
        running and configuration takes effect.
        """
        if self.runtime.is_fake:
            return True

        try:
            if self.command_adapter.unit_status("smbd") == "active":
                logger.info("Attempting graceful config reload for smbd...")
                self.command_adapter.reload_config()
                return True
            else:
                logger.info("smbd is inactive; directly starting/restarting service...")
        except Exception as exc:
            logger.warning("Graceful smbd config reload failed; falling back to restart: %s", exc)

        try:
            self.command_adapter.restart_unit("smbd")
            return True
        except CalledProcessError as exc:
            logger.error("Failed to restart required SMB service smbd: %s", exc)
            return False

    def _restart_services(self):
        """Restart or reload SMB services."""
        if self.runtime.is_fake:
            if self.fake_state is None:
                raise RuntimeError("Fake runtime is missing fake state.")
            self.fake_state.set_smb_services("active", "active", "active")
            logger.info("Fake mode: marked SMB services as active")
            return True

        # Handle smbd via graceful reload / fallback restart
        if not self._reload_or_restart_smbd():
            return False

        for unit_name in ("nmbd", "wsdd2"):
            try:
                self.command_adapter.restart_unit(unit_name)
            except CalledProcessError as exc:
                # Discovery restarts are best-effort. The status API reports
                # the resulting partial state without rolling back share writes.
                logger.warning("Failed to restart discovery service %s: %s", unit_name, exc)

        logger.info("SMB services reload/restart completed successfully")
        return True

    def _restart_required_smbd_after_rollback(self):
        if self.runtime.is_fake:
            if self.fake_state is None:
                raise RuntimeError("Fake runtime is missing fake state.")
            self.fake_state.set_smb_services("active", "active", "active")
            return True
        # Rollback has just restored the owned shares file. Only smbd is
        # required for direct file serving; try graceful reload/fallback restart.
        return self._reload_or_restart_smbd()

    def restart_services(self):
        """Restart SMB services through the public service boundary."""
        return self._restart_services()

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
            if not stripped or stripped.startswith(("#", ";")):
                continue

            section_name = _extract_section_name(stripped)
            if section_name is not None:
                if share_name is not None:
                    raise SMBConfigError(
                        "SimpleSaferServer only supports one share section per parsed share block."
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
            raise SMBConfigError("Failed to find a Samba share section inside a parsed block.")

        if marker_name is not None and share_name != marker_name:
            raise SMBConfigError(
                f"Managed share markers do not match the enclosed share name for '{marker_name}'."
            )

        return ParsedShare(name=share_name, managed=managed, **share_data)

    def _parse_smb_conf(self, content: str) -> Tuple[List[str], List[ParsedShare]]:
        lines = content.splitlines(keepends=True)
        shares = []
        index = 0

        while index < len(lines):
            stripped = lines[index].strip()

            section_name = _extract_section_name(stripped)
            if section_name and section_name.lower() not in SYSTEM_SHARE_NAMES:
                start_line = index
                index += 1

                while index < len(lines):
                    current = lines[index].strip()
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
        unmanaged = self._inspect_unmanaged_effective_shares()
        managed_lines, managed = self._load_managed_shares_file()
        return managed_lines, managed + unmanaged

    def _find_unmanaged_share_record(self, name):
        unmanaged = self._inspect_unmanaged_effective_shares()
        return self._find_share_record(unmanaged, name)

    def _read_sss_shares_file(self):
        try:
            return self.sss_shares_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def _load_managed_shares_file(self):
        lines, shares = self._parse_plain_share_file(self._read_sss_shares_file(), managed=True)
        seen = set()
        for share in shares:
            if share.name in seen:
                raise SMBConfigError(
                    f"The SimpleSaferServer shares file is unsupported or malformed: duplicate share '{share.name}'."
                )
            seen.add(share.name)
        return lines, shares

    def _parse_plain_share_file(self, content: str, *, managed: bool):
        lines = content.splitlines(keepends=True)
        shares = []
        index = 0

        while index < len(lines):
            section_name = _extract_section_name(lines[index].strip())
            if section_name is None:
                index += 1
                continue

            if section_name.lower() in SYSTEM_SHARE_NAMES:
                raise SMBConfigError(
                    f"The SimpleSaferServer shares file is unsupported or malformed: [{section_name}] is not a managed share section."
                )

            start_line = index
            index += 1
            while index < len(lines) and _extract_section_name(lines[index].strip()) is None:
                index += 1

            share = self._parse_share_block(lines[start_line:index], managed=managed)
            share.start_line = start_line
            share.end_line = index
            share.raw_text = "".join(lines[start_line:index])
            shares.append(share)

        return lines, shares

    def _find_share_record(self, shares, name, *, managed=None):
        matches = [
            share
            for share in shares
            if share.name == name and (managed is None or share.managed == managed)
        ]
        if len(matches) > 1:
            raise SMBConfigError(
                f"Multiple Samba shares named '{name}' were found, so SimpleSaferServer cannot act safely. "
                f"See {SMB_DOCS_URL} for manual cleanup guidance."
            )
        return matches[0] if matches else None

    def _validate_share_input(self, name, path):
        if not name or not path:
            raise ValueError("Share name and path are required")
        if (
            not isinstance(name, str)
            or _contains_control_characters(name)
            or not VALID_SHARE_NAME_RE.fullmatch(name)
        ):
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
            if _contains_control_characters(username) or not VALID_SHARE_NAME_RE.fullmatch(
                username
            ):
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
        _, shares = self._load_managed_shares_file()
        return [share.as_dict() for share in shares]

    def list_unmanaged_shares(self):
        _, shares = self._load_shares()
        return [share.as_dict() for share in shares if not share.managed]

    def get_managed_share(self, name):
        _, shares = self._load_managed_shares_file()
        share = self._find_share_record(shares, name, managed=True)
        return share.as_dict() if share else None

    def create_managed_share(self, name, path, writable=True, comment="", valid_users=None):
        self._validate_share_input(name, path)
        self._ensure_layout_for_share_write()

        lines, managed_shares = self._load_managed_shares_file()
        # The owned shares file stays authoritative for SimpleSaferServer
        # ownership, while the effective config check catches administrator
        # shares loaded from smb.conf or its non-SSS includes.
        if (
            self._find_share_record(managed_shares, name, managed=True) is not None
            or self._find_unmanaged_share_record(name) is not None
        ):
            raise ValueError(
                f"Share '{name}' already exists. SimpleSaferServer will not overwrite an existing share "
                f"with the same name. See {SMB_DOCS_URL} for manual conversion guidance."
            )

        block_lines = self._render_managed_share_block(name, path, writable, comment, valid_users)
        new_lines = self._append_managed_block(lines, block_lines)
        self._commit_sss_shares_file("".join(new_lines))

        return True

    def update_managed_share(
        self, old_name, new_name, path, writable=True, comment="", valid_users=None
    ):
        self._validate_share_input(new_name, path)
        self._ensure_layout_for_share_write()

        lines, managed_shares = self._load_managed_shares_file()
        share = self._find_share_record(managed_shares, old_name, managed=True)
        if share is None:
            if self._find_unmanaged_share_record(old_name) is not None:
                raise ValueError(
                    f"Share '{old_name}' is not managed by SimpleSaferServer, so it cannot be edited here. "
                    f"See {SMB_DOCS_URL} for manual conversion guidance."
                )
            raise ValueError(f"Share {old_name} not found")

        managed_conflict = self._find_share_record(managed_shares, new_name, managed=True)
        unmanaged_conflict = None
        if new_name != old_name:
            unmanaged_conflict = self._find_unmanaged_share_record(new_name)
        if managed_conflict is not None and managed_conflict.name != old_name:
            raise ValueError(
                f"Share '{new_name}' already exists. SimpleSaferServer will not overwrite an existing share "
                f"with the same name. See {SMB_DOCS_URL} for manual conversion guidance."
            )
        if unmanaged_conflict is not None:
            raise ValueError(
                f"Share '{new_name}' already exists. SimpleSaferServer will not overwrite an existing share "
                f"with the same name. See {SMB_DOCS_URL} for manual conversion guidance."
            )

        new_lines = list(lines)
        replacement = self._render_managed_share_block(
            new_name, path, writable, comment, valid_users
        )
        new_lines[share.start_line : share.end_line] = replacement
        self._commit_sss_shares_file("".join(new_lines))

        return True

    def delete_managed_share(self, name):
        self._ensure_layout_for_share_write()
        lines, managed_shares = self._load_managed_shares_file()
        share = self._find_share_record(managed_shares, name, managed=True)
        if share is None:
            if self._find_unmanaged_share_record(name) is not None:
                raise ValueError(
                    f"Share '{name}' is not managed by SimpleSaferServer, so it cannot be deleted here. "
                    f"See {SMB_DOCS_URL} for manual conversion guidance."
                )
            raise ValueError(f"Share {name} not found")

        new_lines = list(lines)
        del new_lines[share.start_line : share.end_line]
        self._commit_sss_shares_file("".join(new_lines))

        return True

    def ensure_default_backup_share(
        self, mount_point, admin_username, fake_mode_comment=None, comment=None
    ):
        if comment is None and self.runtime.is_fake and fake_mode_comment is not None:
            comment = fake_mode_comment
        elif comment is None and self.runtime.is_fake:
            comment = "Fake-mode backup share"
        elif comment is None:
            comment = "Default backup share created by SimpleSaferServer setup"

        unmanaged_backup = self._find_unmanaged_share_record("backup")
        if unmanaged_backup is not None:
            raise ValueError(
                'Samba share "backup" already exists. Rename or remove it, then retry.'
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

    def _get_managed_share_or_raise(self, share_name):
        # Check the owned shares file first so that a broken admin-owned Samba
        # include never blocks routine management of SimpleSaferServer shares.
        _, managed_shares = self._load_managed_shares_file()
        share = self._find_share_record(managed_shares, share_name, managed=True)
        if share is not None:
            return share.as_dict()

        # Share not in the owned file. Inspect unmanaged shares to distinguish
        # "exists but not managed" from "does not exist anywhere".
        try:
            unmanaged = self._inspect_unmanaged_effective_shares()
            if self._find_share_record(unmanaged, share_name) is not None:
                raise ValueError(
                    f"Share '{share_name}' is not managed by SimpleSaferServer, so it cannot be edited here. "
                    f"See {SMB_DOCS_URL} for manual conversion guidance."
                )
        except SMBConfigError:
            # Effective config inspection failed — we already know the share is
            # not in the owned file, so report it as not found.
            pass

        raise ValueError(f"Share {share_name} not found")

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
            if self.fake_state is None:
                raise RuntimeError("Fake runtime is missing fake state.")
            return self.fake_state.get_smb_services()

        statuses = {}
        for unit_name in ("smbd", "nmbd"):
            try:
                statuses[unit_name] = self.command_adapter.unit_status(unit_name)
            except Exception as exc:
                logger.error("Error getting %s status: %s", unit_name, exc)
                statuses[unit_name] = "error"

        try:
            statuses["wsdd2"] = self.command_adapter.unit_status("wsdd2")
        except Exception as exc:
            # wsdd2 is optional on older distributions, so a missing unit is
            # surfaced as unavailable instead of collapsing the whole response.
            logger.info("wsdd2 status unavailable: %s", exc)
            statuses["wsdd2"] = "unavailable"

        return statuses
