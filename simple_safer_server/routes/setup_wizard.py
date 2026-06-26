import logging
from datetime import UTC, datetime
from functools import wraps

from flask import Blueprint, current_app, redirect, render_template, session

from simple_safer_server.core.backup_readiness import build_backup_readiness
from simple_safer_server.core.module_lifecycle import (
    ModuleLifecycleError,
    apply_module,
    ensure_module_can_apply,
)
from simple_safer_server.core.module_serialization import module_data, module_plan_data
from simple_safer_server.core.ownership import record_runtime_owned_resource
from simple_safer_server.core.privileged_client import (
    PrivilegedActionClient,
    PrivilegedActionClientError,
)
from simple_safer_server.modules.alerts.module import create_module as create_alerts_module
from simple_safer_server.modules.cloud_backup import normalize_bandwidth_limit
from simple_safer_server.modules.cloud_backup.module import (
    create_module as create_cloud_backup_module,
)
from simple_safer_server.modules.storage.backup_drive_setup import BackupDriveSetupError
from simple_safer_server.modules.storage.backup_drive_setup import (
    list_available_drives as get_available_backup_drives,
)
from simple_safer_server.modules.storage.location import (
    StorageLocationError,
    configure_existing_folder,
    marker_path,
)
from simple_safer_server.modules.storage.module import create_module as create_storage_module
from simple_safer_server.services.config_manager import ConfigManager
from simple_safer_server.services.filesystem_browser import list_local_path
from simple_safer_server.services.runtime import get_runtime
from simple_safer_server.services.schedule_time import (
    ScheduleTimeError,
    normalize_ui_schedule_time,
)
from simple_safer_server.services.server_identity import (
    SERVER_NAME_HELP_TEXT,
    ServerIdentityError,
    ServerIdentityService,
)
from simple_safer_server.services.user_manager import UserManager
from simple_safer_server.web.api import json_data, json_problem, json_request_data
from simple_safer_server.web.i18n import gettext
from simple_safer_server.web.problems import (
    ApiProblem,
    ConflictProblem,
    ForbiddenProblem,
    OperationProblem,
    UnauthorizedProblem,
    ValidationProblem,
)

setup = Blueprint('setup', __name__)
runtime = None
config_manager = None
user_manager = None
server_identity_service = None
logger = logging.getLogger(__name__)


def _validation_problem(message, **extra):
    return json_problem(ValidationProblem(message, slug='setup-validation-error', extra=extra))


def _operation_problem(message, **extra):
    return json_problem(OperationProblem(message, slug='setup-operation-failed', extra=extra))


def _module_setup_problem(error):
    return json_problem(
        ConflictProblem(
            str(error),
            title=gettext("Module setup required"),
            slug="module-setup-required",
        )
    )


def _cloud_backup_service():
    """Return the shared cloud-backup service registered by the app factory."""
    return current_app.extensions["simple_safer_server"].cloud_backup_service


def _storage_command_runner():
    """Return the app command runner for storage mount identity checks."""
    services = current_app.extensions.get("simple_safer_server")
    if services is not None and hasattr(services, "command_runner"):
        return services.command_runner
    return None


def _privileged_actions():
    """Return the shared helper client, with fallback support for route tests."""
    services = current_app.extensions.get("simple_safer_server")
    if services is not None and hasattr(services, "privileged_actions"):
        return services.privileged_actions
    return PrivilegedActionClient()


def _runtime():
    """Return the active runtime, including fake-mode test/runtime overrides."""
    services = current_app.extensions.get("simple_safer_server")
    if services is not None and hasattr(services, "runtime"):
        return services.runtime
    if runtime is not None:
        return runtime
    return get_runtime()


def _config_manager():
    """Return the shared config manager without creating one at import time."""
    services = current_app.extensions.get("simple_safer_server")
    if services is not None and hasattr(services, "config_manager"):
        return services.config_manager
    if config_manager is not None:
        return config_manager
    return ConfigManager(runtime=_runtime())


def _user_manager():
    """Return the shared user manager so setup user writes use helper-backed services."""
    services = current_app.extensions.get("simple_safer_server")
    if services is not None and hasattr(services, "user_manager"):
        return services.user_manager
    if user_manager is not None:
        return user_manager
    try:
        return UserManager(runtime=_runtime(), privileged_actions=_privileged_actions())
    except TypeError:
        # Route tests replace UserManager with a tiny constructor that only
        # accepts runtime. The real app path above uses app.extensions.
        return UserManager(runtime=_runtime())


def _prepare_module_setup(module):
    """Check module setup requirements before setup routes perform host writes."""
    ensure_module_can_apply(module)


def _record_module_setup(module):
    """Record module ownership after setup routes finish the host write."""
    apply_module(module, _runtime())


def _record_storage_marker_write(storage_path: str):
    """Record the exact marker file written by existing-folder setup."""
    record_runtime_owned_resource(
        _runtime(),
        "storage",
        kind="marker-file",
        identifier=str(marker_path(storage_path)),
        reason="Confirm cloud backup is reading the intended storage location.",
    )


def _server_identity_service():
    """Return the shared server-identity service, with test fallback support."""
    services = current_app.extensions.get("simple_safer_server")
    if services is not None and hasattr(services, "server_identity_service"):
        return services.server_identity_service
    if server_identity_service is not None:
        return server_identity_service
    return ServerIdentityService(config_manager=_config_manager(), runtime=_runtime())


def _backup_readiness():
    """Return the shared backup-protection checklist used by setup and dashboard UI."""
    services = current_app.extensions.get("simple_safer_server")
    active_config_manager = (
        services.config_manager
        if services is not None and hasattr(services, "config_manager")
        else _config_manager()
    )
    active_smb_manager = (
        services.smb_manager if services is not None and hasattr(services, "smb_manager") else None
    )
    active_runtime = (
        services.runtime if services is not None and hasattr(services, "runtime") else _runtime()
    )
    return build_backup_readiness(
        active_config_manager,
        runtime=active_runtime,
        smb_manager=active_smb_manager,
    )


def _setup_module_plans():
    """Build read-only setup plan previews for modules configured by onboarding."""
    active_runtime = _runtime()
    modules = {
        "storage": create_storage_module(),
        "cloud_backup": create_cloud_backup_module(),
        "alerts": create_alerts_module(),
    }
    return {
        key: {
            "module": module_data(module, active_runtime),
            "plan": module_plan_data(module.build_plan()),
        }
        for key, module in modules.items()
    }


def _setup_ui_text():
    """Return browser copy used by the setup wizard script."""
    _ = gettext
    return {
        "driveTypes": {
            "usb": _("USB Drive"),
            "removable": _("Removable Drive"),
            "internal": _("Internal Drive"),
        },
        "storage": {
            "selectDrive": _("Select a drive…"),
            "unmountedReady": _("Unmounted (ready for formatting)"),
            "mounted": _("Mounted"),
            "mountedAtTemplate": _(" (Mounted at {mountpoint})"),
            "unmountedSuffix": _("[unmounted]"),
            "refreshingDrives": _("Refreshing drives…"),
            "driveListRefreshed": _("Drive list refreshed."),
            "loadFormatDrivesFailed": _("Failed to load drives for formatting"),
            "refreshDrivesFailed": _("Failed to refresh drives."),
            "refreshingPartitions": _("Refreshing partitions…"),
            "partitionListRefreshed": _("Partition list refreshed."),
            "loadMountDrivesFailed": _("Failed to load NTFS drives for mounting"),
            "refreshPartitionsFailed": _("Failed to refresh partitions."),
            "selectDriveFirst": _("Please select a drive first."),
            "formattingDrive": _("Formatting drive…"),
            "driveFormatted": _("Drive formatted successfully."),
            "formatDriveFailed": _("Failed to format drive."),
            "formatDriveError": _("An error occurred while formatting the drive"),
            "unmountingDrive": _("Unmounting drive…"),
            "driveUnmountedForFormat": _("Drive unmounted. You can continue formatting."),
            "unmountDriveFailed": _("Failed to unmount drive."),
            "unmountDriveError": _("An error occurred while unmounting the drive"),
            "selectDriveToMount": _("Please select a drive to mount"),
            "selectDriveShort": _("Please select a drive."),
            "mountingDrive": _("Mounting drive…"),
            "driveMounted": _("Drive mounted successfully."),
            "mountDriveFailed": _("Failed to mount drive."),
            "mountDriveError": _("An error occurred while mounting the drive"),
            "existingFolderRequired": _("Enter the folder path to use for storage."),
            "existingFolderFailed": _("Could not use this folder."),
            "retryManagedUnmount": _("Retrying with the SMB-safe unmount path…"),
            "driveUnmountedForMount": _(
                "Drive unmounted. You can continue mounting the selected partition."
            ),
        },
        "alerts": {
            "correctFields": _("Please correct the highlighted fields."),
            "allEmailFieldsRequired": _("Please fill in all email fields"),
            "setupEmailPrefix": _("Error setting up email: "),
            "setupEmailFallback": _("An error occurred while setting up email"),
        },
        "schedule": {
            "correctFields": _("Please correct the highlighted fields."),
            "selectBackupTime": _("Please select a backup time."),
            "saveSchedulePrefix": _("Error saving schedule: "),
        },
        "cloudBackup": {
            "skipFailed": _("Could not skip cloud backup."),
            "connectMegaFailed": _("Error connecting to MEGA."),
            "saveMegaFailed": _("Error saving MEGA config."),
            "saveRcloneFailed": _("Error saving rclone config."),
        },
        "folderPicker": {
            "mega": {
                "loading": _("Loading..."),
                "emptyMessage": _("No subfolders in this directory."),
                "credentialsRequired": _("MEGA credentials are required before creating a folder."),
                "loadFailed": _("Could not load folders."),
                "createFailed": _("Error creating folder."),
            },
            "local": {
                "loading": _("Loading..."),
                "emptyMessage": _("No folders or files in this directory."),
                "loadFailed": _("Could not load folders."),
            },
        },
        "completion": {
            "missingPrefix": _("Setup is still missing: "),
            "missingSuffix": _("."),
            "missingRequired": _("Setup is still missing a few required details."),
            "failed": _("Could not complete setup."),
            "fieldLabels": {
                "backup.email_address": _("backup alert email address"),
                "backup.mount_point": _("storage location"),
                "backup.uuid": _("managed drive selection"),
                "storage.mode": _("storage choice"),
                "storage.path": _("storage folder"),
                "storage.storage_id": _("storage marker"),
                "email.email_from_address": _("email sender address"),
                "email.smtp_server": _("SMTP server"),
                "email.smtp_port": _("SMTP port"),
                "email.smtp_user": _("SMTP username"),
                "email.smtp_password": _("SMTP password"),
                "schedule.backup_cloud_time": _("cloud backup schedule"),
                "schedule.bandwidth_limit": _("bandwidth limit"),
                "system.server_name": _("server name"),
                "user.username": _("admin username"),
            },
        },
        "admin": {
            "correctFields": _("Please correct the highlighted fields."),
            "createUserPrefix": _("Error creating user: "),
            "createUserFallback": _("An error occurred while creating the user"),
            "configureSystemPrefix": _("Error configuring system: "),
            "configureSystemFallback": _("An error occurred while configuring the system"),
        },
    }


def _render_setup_page():
    try:
        readiness = _backup_readiness()
    except Exception as exc:
        logger.error("Error building setup readiness checklist for page: %s", exc)
        readiness = None
    return render_template(
        'setup.html',
        server_name_help_text=SERVER_NAME_HELP_TEXT,
        backup_readiness=readiness,
        setup_module_plans=_setup_module_plans(),
        setup_ui_text=_setup_ui_text(),
    )


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
        active_config_manager = _config_manager()
        # Once setup is complete these routes become admin maintenance tools,
        # so old bookmarked setup URLs must not keep working anonymously.
        if not active_config_manager.is_setup_complete():
            return route_handler(*args, **kwargs)

        if 'username' not in session:
            return json_problem(
                UnauthorizedProblem('Please log in again.', slug='setup-login-required')
            )

        # Reload user data to ensure admin checks use the latest persisted roles.
        active_user_manager = _user_manager()
        active_user_manager.reload_users()
        if not active_user_manager.is_admin(session['username']):
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


def _managed_unmount_retry_problem():
    return ValidationProblem(
        MANAGED_UNMOUNT_RETRY_ERROR,
        slug='setup-managed-unmount-retry-available',
        extra={
            'details': MANAGED_UNMOUNT_RETRY_DETAILS,
            'can_retry_managed_unmount': True,
        },
    )


@setup.route('/setup')
def setup_page():
    """Render the setup wizard page"""
    try:
        # Setup routes still support module-level test seams, while shared
        # services write through the app-factory ConfigManager. Reload before
        # validation so cross-service setup writes are visible immediately.
        active_config_manager = _config_manager()
        active_config_manager.load_config()
        current_config = active_config_manager.get_all_config()
        # Log section names only; setup config can include admin contact details
        # and managed service paths that do not belong in routine logs.
        logger.debug(
            "Checking setup status with config sections: %s", sorted(current_config.keys())
        )

        # Check if setup is complete
        if active_config_manager.is_setup_complete():
            logger.info("Setup is complete, redirecting to main page")
            return redirect('/')

        # Check if we have all required fields
        required_fields = {
            'system': ['username', 'server_name'],
            'backup': ['mount_point', 'email_address'],
            'storage': ['mode', 'path', 'storage_id'],
            'schedule': ['backup_cloud_time'],
        }
        storage_mode = current_config.get('storage', {}).get('mode', 'existing_folder')
        cloud_enabled = (
            str(current_config.get('backup', {}).get('cloud_enabled', 'false')).lower() == 'true'
        )
        if storage_mode == 'managed_drive':
            required_fields['backup'].append('uuid')
        if cloud_enabled:
            required_fields['backup'].append('rclone_dir')

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
            return _render_setup_page()

        # Do NOT mark setup as complete here. Only do so in /api/setup/complete.
        return _render_setup_page()

    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error checking setup status: {e}")
        return _render_setup_page()


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

        active_config_manager = _config_manager()
        success, message = _user_manager().create_user(username, password, is_admin=True)
        if success:
            # The setup admin is the account Samba and completion checks must
            # use later; keep this tied to the account creation step so the
            # system-info step cannot drift into a second source of truth.
            active_config_manager.set_value('system', 'username', username)
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
        # the "set up or erase this disk" step, not the "pick an NTFS backup
        # partition" step.
        drives = get_available_backup_drives(runtime=_runtime(), ntfs_only=False)
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
        # it must reuse the same NTFS scan as the Storage managed-drive flow. That
        # includes the blkid fallback when lsblk reports ntfs-3g mounts as
        # fuseblk, which is easy to miss if this route ever gets "simplified".
        drives = get_available_backup_drives(runtime=_runtime(), ntfs_only=True)
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
        _prepare_module_setup(create_storage_module())
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

        if not isinstance(disk, str):
            return _validation_problem('Invalid disk path: must be a string')

        if not disk:
            return _validation_problem('No disk selected')

        result = _privileged_actions().run('storage.format', {'disk': disk})
        return json_data(
            {'result': result.data}, message=result.data.get('message', 'Drive formatted.')
        )

    except PrivilegedActionClientError as e:
        if e.exit_code == 2:
            return _validation_problem(str(e))
        logger.error("Privileged format action failed: %s", e)
        return _operation_problem(
            'Error formatting drive',
            details='An unexpected error occurred. Please check the system logs for more information.',
        )
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
        _prepare_module_setup(create_storage_module())
        data = json_request_data()
        # The setup wizard uses this route for two different UI controls:
        # whole-disk unmount before formatting, and exact-partition unmount
        # before mounting an NTFS partition in step 3.
        disk = data.get('disk')
        partition = data.get('partition')
        force_managed = bool(data.get('force_managed'))
        result = _privileged_actions().run(
            'storage.unmount',
            {
                'disk': disk or '',
                'partition': partition or '',
                'force_managed': force_managed,
            },
        )
        if result.data.get('can_retry_managed_unmount'):
            return json_problem(_managed_unmount_retry_problem())
        return json_data(message=result.data.get('message', 'Drive unmounted.'))
    except PrivilegedActionClientError as e:
        if e.exit_code == 2:
            return _validation_problem(str(e))
        logger.error("Privileged unmount action failed: %s", e)
        return _operation_problem(
            f'Error unmounting drive: {e!s}',
            details='An unexpected error occurred. Please check the system logs for more information.',
        )
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
        storage_module = create_storage_module()
        _prepare_module_setup(storage_module)
        data = json_request_data()
        # Step 3 always selects a filesystem-bearing partition, never a whole
        # disk. That aligns it with the managed-drive flow on Storage.
        partition = data.get('partition')
        if not partition:
            return _validation_problem('partition is required')
        active_runtime = _runtime()
        mount_point = data.get('mount_point') or active_runtime.default_mount_point
        # SimpleSaferServer-managed backup drives are always registered for boot
        # remounts by the allowlisted managed-drive helper action.
        result = _privileged_actions().run(
            'storage.managed-drive',
            {
                'partition': partition,
                'mount_point': mount_point,
                'ntfs_driver': data.get('ntfs_driver', 'ntfs-3g'),
            },
        )
        logger.info(
            "Backup drive mounted successfully at %s",
            result.data.get('mount_point', mount_point),
        )
        _record_module_setup(storage_module)
        return json_data(message=result.data.get('message', 'Backup drive mounted successfully.'))
    except BackupDriveSetupError as e:
        return _validation_problem(str(e), details=e.details)
    except PrivilegedActionClientError as e:
        if e.exit_code == 2:
            return _validation_problem(str(e))
        logger.error("Privileged backup drive setup action failed: %s", e)
        return _operation_problem(
            'Error mounting drive',
            details='An unexpected error occurred. Please check the system logs for more information.',
        )
    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error mounting drive: {e!s}")
        return _operation_problem(
            f'Error mounting drive: {e!s}',
            details='An unexpected error occurred. Please check the system logs for more information.',
        )


@setup.route('/api/setup/existing-folder', methods=['POST'])
@setup_api_access_required
def setup_existing_folder():
    """Use a folder that is already managed or mounted outside SimpleSaferServer."""
    try:
        storage_module = create_storage_module()
        _prepare_module_setup(storage_module)
        data = json_request_data()
        active_runtime = _runtime()
        active_config_manager = _config_manager()
        location = configure_existing_folder(
            active_config_manager,
            data.get('path', ''),
            runtime=active_runtime,
            command_runner=_storage_command_runner(),
        )
        _record_storage_marker_write(location.path)
        _record_module_setup(storage_module)
        return json_data(
            {
                'path': location.path,
                'mode': location.mode,
            },
            message='Storage folder saved.',
        )
    except StorageLocationError as exc:
        return _validation_problem(str(exc))
    except ApiProblem:
        raise
    except Exception as exc:
        logger.error("Error configuring existing storage folder: %s", exc)
        return _operation_problem('Could not configure the storage folder')


@setup.route('/api/setup/list-path', methods=['POST'])
@setup_api_access_required
def setup_list_path():
    """List local folders and files for the existing-folder setup picker."""
    try:
        data = json_request_data()
        return json_data(list_local_path(data.get('path', '/')))
    except NotADirectoryError as exc:
        return _validation_problem(str(exc))
    except ApiProblem:
        raise
    except OSError as exc:
        logger.error("Error listing local setup picker path: %s", exc)
        return _operation_problem('Could not list that folder')


@setup.route('/api/setup/cloud-backup/skip', methods=['POST'])
@setup_api_access_required
def skip_cloud_backup():
    """Allow local-only setup without forcing an rclone destination."""
    try:
        active_config_manager = _config_manager()
        active_config_manager.set_value('backup', 'cloud_enabled', 'false')
        active_config_manager.set_value('backup', 'cloud_skipped', 'true')
        active_config_manager.set_value('backup', 'cloud_mode', '')
        active_config_manager.set_value('backup', 'rclone_dir', '')
        return json_data(message='Cloud backup skipped.')
    except ApiProblem:
        raise
    except Exception as exc:
        logger.error("Error skipping cloud backup: %s", exc)
        return _operation_problem('Could not skip cloud backup')


@setup.route('/api/setup/rclone', methods=['POST'])
@setup_api_access_required
def setup_rclone():
    """Set up advanced rclone configuration through the shared backup service."""
    try:
        data = json_request_data()
        config = data.get('config')
        remote_name = data.get('remote_name')

        if not config or not remote_name:
            return _validation_problem('Config and remote name are required')

        cloud_backup_module = create_cloud_backup_module()
        _prepare_module_setup(cloud_backup_module)
        # The cloud-backup service owns rclone persistence and mode flags for
        # every cloud configuration flow.
        _cloud_backup_service().save_config(
            {
                'cloud_mode': 'advanced',
                'rclone_config': config,
                'remote_name': remote_name,
            }
        )
        _record_module_setup(cloud_backup_module)

        return json_data()
    except ModuleLifecycleError as exc:
        return _module_setup_problem(exc)
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
        # Validate and write the same canonical value so the saved SMTP config
        # never keeps whitespace that happened to pass the numeric port check.
        smtp_port = str(smtp_port).strip()
        if not _valid_tcp_port(smtp_port):
            return _validation_problem('SMTP port must be between 1 and 65535')

        alerts_module = create_alerts_module()
        _prepare_module_setup(alerts_module)
        try:
            _privileged_actions().run(
                'alerts.write-smtp-config',
                {
                    'from_address': from_address,
                    'smtp_server': smtp_server,
                    'smtp_port': smtp_port,
                    'smtp_username': smtp_username,
                    'smtp_password': smtp_password,
                },
            )
        except PrivilegedActionClientError:
            return _operation_problem('Failed to write SMTP configuration')

        # Persist the UI-facing addresses only after SMTP config is safely written.
        active_config_manager = _config_manager()
        active_config_manager.set_value('backup', 'email_address', email)
        active_config_manager.set_value('backup', 'from_address', from_address)
        _record_module_setup(alerts_module)

        return json_data()
    except ModuleLifecycleError as exc:
        return _module_setup_problem(exc)
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

        try:
            schedule_time = normalize_ui_schedule_time(schedule_time)
        except ScheduleTimeError:
            return _validation_problem(
                'Invalid time format',
                details='Time must be in HH:MM format (24-hour)',
            )

        # Store the same HH:MM shape emitted by browser time inputs so the worker
        # scheduler does not need to guess which UI contract produced it.
        active_config_manager = _config_manager()
        active_config_manager.set_value('schedule', 'backup_cloud_time', schedule_time)
        active_config_manager.set_value('schedule', 'configured', 'true')
        if bandwidth_limit is not None:
            active_config_manager.set_value('backup', 'bandwidth_limit', bandwidth_limit)

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


@setup.route('/api/setup/complete', methods=['POST'])
@setup_api_access_required
def complete_setup():
    """Complete the setup process"""
    try:
        # Cloud-backup setup writes through the shared app-factory service; this
        # module-level manager must reload before final missing-field checks and
        # systemd generation use the setup snapshot.
        active_config_manager = _config_manager()
        active_user_manager = _user_manager()
        active_config_manager.load_config()
        current_config = active_config_manager.get_all_config()
        # The validation loop below logs only missing section/field names.
        logger.debug("Completing setup after loading current configuration")

        # Validate required fields
        required_fields = {
            'system': ['username', 'server_name'],
            'backup': ['mount_point', 'email_address'],
            'storage': ['mode', 'path', 'storage_id'],
            'schedule': ['backup_cloud_time'],
        }
        storage_mode = current_config.get('storage', {}).get('mode', 'existing_folder')
        cloud_enabled = (
            str(current_config.get('backup', {}).get('cloud_enabled', 'false')).lower() == 'true'
        )
        if storage_mode == 'managed_drive':
            required_fields['backup'].append('uuid')
        if cloud_enabled:
            required_fields['backup'].append('rclone_dir')

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

        if str(current_config.get('schedule', {}).get('configured', 'false')).lower() != 'true':
            return _validation_problem(
                'Missing required fields',
                details=['Missing schedule.configured'],
            )

        # Update the user's last login time since they completed the setup
        if 'username' in session:
            username = session['username']
            if username in active_user_manager.users:
                active_user_manager.users[username]['last_login'] = str(datetime.now(UTC))
                active_user_manager._save_users()
                logger.info(f"Updated last login time for user {username} after setup completion")

        # Completing first-run records the saved choices. Optional host setup
        # belongs to module apply flows so the admin can review each plan first.
        active_config_manager.mark_setup_complete()
        active_config_manager.load_config()  # Ensure in-memory config is up to date

        logger.info("Setup completed successfully.")
        return json_data()

    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error completing setup: {e!s}")
        return _operation_problem(
            'Error completing setup',
            details='An unexpected error occurred. Please check the system logs for more information.',
        )


@setup.route('/api/setup/readiness', methods=['GET'])
@setup_api_access_required
def setup_readiness():
    """Return the shared 3-2-1 backup-protection checklist."""
    try:
        return json_data(_backup_readiness())
    except ApiProblem:
        raise
    except Exception as exc:
        logger.error("Error building setup readiness checklist: %s", exc)
        return _operation_problem('Could not build setup checklist')


@setup.route('/api/setup/system', methods=['POST'])
@setup_api_access_required
def setup_system_info():
    """Save system-level info after the admin account has been created."""
    try:
        data = json_request_data()
        server_name = data.get('server_name')

        if not server_name:
            return _validation_problem('Server name is required')

        _server_identity_service().save_server_name(server_name)
        return json_data()
    except ServerIdentityError as e:
        return _validation_problem(str(e))
    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error saving system info: {e}")
        return _operation_problem('Could not save system information')


@setup.route('/api/setup/mega/connect', methods=['POST'])
@setup_api_access_required
def mega_connect():
    """Authenticate with MEGA and return root folders using the shared service."""
    try:
        data = json_request_data()
        email = data.get('email')
        password = data.get('password')
        if not email or not password:
            return _validation_problem('Email and password are required.')
        folder_list = _cloud_backup_service().list_mega_folders(
            {'email': email, 'password': password, 'path': '/'}
        )
        return json_data({'folders': folder_list.folders})
    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error connecting to MEGA: {e!s}")
        return _operation_problem('Error connecting to MEGA')


@setup.route('/api/setup/mega/list_folders', methods=['POST'])
@setup_api_access_required
def mega_list_folders():
    """List folders at a given MEGA path using the shared service."""
    try:
        data = json_request_data()
        path = data.get('path', '/')
        email = data.get('email')
        password = data.get('password')
        if not email or not password:
            return _validation_problem('Email and password are required.')
        folder_list = _cloud_backup_service().list_mega_folders(
            {'email': email, 'password': password, 'path': path}
        )
        return json_data(folder_list)
    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error listing MEGA folders: {e!s}")
        return _operation_problem('Error listing MEGA folders')


@setup.route('/api/setup/mega/create_folder', methods=['POST'])
@setup_api_access_required
def mega_create_folder_picker():
    """Create a new MEGA folder using the shared service."""
    try:
        data = json_request_data()
        folder_name = data.get('folder_name')
        path = data.get('path', '/')
        email = data.get('email')
        password = data.get('password')
        if not folder_name or not email or not password:
            return _validation_problem('Folder name, email, and password are required.')
        _cloud_backup_service().create_mega_folder(
            {'email': email, 'password': password, 'path': path, 'folder_name': folder_name}
        )
        return json_data()
    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error creating MEGA folder: {e!s}")
        return _operation_problem('Error creating folder')


@setup.route('/api/setup/mega/save', methods=['POST'])
@setup_api_access_required
def mega_save():
    """Save MEGA credentials and selected folder through the shared backup service."""
    try:
        data = json_request_data()
        email = data.get('email')
        password = data.get('password')
        folder = data.get('folder')
        if not email or not password or not folder:
            return _validation_problem('Email, password, and folder are required.')
        cloud_backup_module = create_cloud_backup_module()
        _prepare_module_setup(cloud_backup_module)
        # The service keeps rclone writes before config writes for every
        # cloud-backup setup path.
        _cloud_backup_service().save_config(
            {
                'cloud_mode': 'mega',
                'mega_email': email,
                'mega_password': password,
                'mega_folder': folder,
            }
        )
        _record_module_setup(cloud_backup_module)
        return json_data()
    except ModuleLifecycleError as exc:
        return _module_setup_problem(exc)
    except ApiProblem:
        raise
    except Exception as e:
        logger.error(f"Error saving MEGA config: {e!s}")
        return _operation_problem('Error saving MEGA config')
