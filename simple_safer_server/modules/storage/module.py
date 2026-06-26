from __future__ import annotations

from simple_safer_server.core.jobs import JobDefinition
from simple_safer_server.core.module_contract import (
    HelpEntry,
    ModuleHelp,
    ModuleNavItem,
    ModuleRoute,
    ModuleState,
    OwnedResource,
    PlanChange,
    PrivilegedAction,
    RequiredTool,
    SssModule,
)


def create_module() -> SssModule:
    return SssModule(
        slug="storage",
        title="Storage",
        description="Chooses and validates the folder used for backup data.",
        state=ModuleState.ACTIVE,
        routes=(
            ModuleRoute(rule="/storage", endpoint="storage_routes.storage_page", page=True),
            ModuleRoute(
                rule="/storage/change-drive",
                endpoint="storage_routes.storage_change_drive_page",
                page=True,
            ),
            ModuleRoute(
                rule="/storage/existing-folder",
                endpoint="storage_routes.storage_existing_folder_page",
                page=True,
            ),
            ModuleRoute(rule="/api/storage/status", endpoint="storage_routes.api_storage_status"),
            ModuleRoute(
                rule="/api/storage/safety-check",
                endpoint="storage_routes.api_storage_safety_check",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/unmount",
                endpoint="storage_routes.unmount",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/restart",
                endpoint="storage_routes.restart",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/shutdown",
                endpoint="storage_routes.shutdown",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/mount",
                endpoint="storage_routes.dashboard_mount_drive",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/system/resources",
                endpoint="storage_routes.api_system_resources",
            ),
            ModuleRoute(
                rule="/api/backup_drive/drives",
                endpoint="storage_routes.api_backup_drive_drives",
            ),
            ModuleRoute(
                rule="/api/backup_drive/format-drives",
                endpoint="storage_routes.api_backup_drive_format_drives",
            ),
            ModuleRoute(
                rule="/api/backup_drive/format",
                endpoint="storage_routes.api_backup_drive_format",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/backup_drive/unmount",
                endpoint="storage_routes.api_backup_drive_unmount",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/backup_drive/configure",
                endpoint="storage_routes.api_backup_drive_configure",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/storage/existing-folder",
                endpoint="storage_routes.api_existing_folder",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/storage/list-path",
                endpoint="storage_routes.api_storage_list_path",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/storage/repair-marker",
                endpoint="storage_routes.api_repair_storage_marker",
                methods=("POST",),
            ),
        ),
        nav_items=(
            ModuleNavItem(
                label="Storage",
                endpoint="storage_routes.storage_page",
                icon="fas fa-folder-tree fa-fw",
                order=40,
                active_endpoints=(
                    "storage_routes.storage_page",
                    "storage_routes.storage_change_drive_page",
                    "storage_routes.storage_existing_folder_page",
                ),
            ),
        ),
        jobs=(
            JobDefinition(
                name="mount-check",
                module_slug="storage",
                title="Mount Check",
                description="Checks and remounts the explicitly managed backup drive.",
                task_name="Check Mount",
                daily_time_config_section="schedule",
                daily_time_config_key="backup_cloud_time",
                default_daily_time="03:00",
                daily_time_offset_minutes=-4,
                enabled_config_section="storage",
                enabled_config_key="mode",
                enabled_config_value="managed_drive",
            ),
        ),
        help=ModuleHelp(
            purpose="Storage is where backup data lands before any cloud copy runs.",
            setup_intro=(
                "Use an existing folder by default. Managed drive setup is an explicit "
                "advanced path."
            ),
            warnings=(
                "Formatting or remounting drives can destroy data or interrupt file sharing.",
            ),
            docs_path="docs/storage.md",
            field_help=(
                HelpEntry(
                    key="existing_folder",
                    text="Use this when another tool or the operating system already manages the storage folder.",
                ),
                HelpEntry(
                    key="managed_drive",
                    text="Use this only when SSS should mount one backup drive for you.",
                ),
                HelpEntry(
                    key="mount_point",
                    text="Where SSS mounts the managed backup partition.",
                ),
                HelpEntry(
                    key="ntfs_driver",
                    text="Use ntfs-3g unless this host is known to work better with the kernel ntfs3 driver.",
                ),
            ),
            confirmations=(
                HelpEntry(
                    key="format_drive",
                    text="Formatting erases the selected drive. Continue only when the selected disk is the backup disk.",
                ),
                HelpEntry(
                    key="use_managed_drive",
                    text="SSS will mount this partition, write its managed fstab entry, and move the backup share to it.",
                ),
            ),
            empty_states=(
                HelpEntry(
                    key="not_configured",
                    text="Storage is not ready. Choose an existing folder or set up a managed drive.",
                ),
            ),
            success_messages=(
                HelpEntry(
                    key="storage_ready",
                    text="Storage is ready for local backups and cloud safety checks.",
                ),
            ),
            error_explanations=(
                HelpEntry(
                    key="marker_missing",
                    text="The storage marker is missing, so SSS cannot prove this is the intended backup folder.",
                ),
            ),
            recovery_actions=(
                HelpEntry(
                    key="marker_missing",
                    text="If this is the correct folder, repair the marker from Storage. If not, mount or choose the correct storage.",
                ),
            ),
        ),
        required_tools=(
            RequiredTool(
                name="lsblk",
                purpose="Lists disks and partitions for advanced managed-drive setup.",
                optional=True,
            ),
            RequiredTool(
                name="blkid",
                purpose="Reads filesystem UUIDs before SSS writes a managed fstab entry.",
                optional=True,
            ),
            RequiredTool(
                name="sfdisk",
                purpose="Creates a fresh partition table when the admin formats a selected backup disk.",
                optional=True,
            ),
            RequiredTool(
                name="mkfs.ntfs",
                purpose="Formats the selected managed-drive partition as NTFS.",
                optional=True,
            ),
            RequiredTool(
                name="ntfs-3g",
                purpose="Mounts NTFS backup drives on hosts that do not use the kernel ntfs3 driver.",
                optional=True,
            ),
        ),
        owned_resources=(
            OwnedResource(
                kind="config-section",
                identifier="<config>/config.conf[storage]",
                reason="Remember whether storage uses an existing folder or an explicit managed drive.",
            ),
            OwnedResource(
                kind="marker-file",
                identifier="<storage>/.simple-safer-server/storage.json",
                reason="Confirm cloud backup is reading the intended storage location.",
                record_on_apply=False,
            ),
            OwnedResource(
                kind="fstab-entry",
                identifier="/etc/fstab#SimpleSaferServer managed backup drive",
                reason="Mount only the explicitly managed backup drive.",
                record_on_apply=False,
            ),
        ),
        privileged_actions=(
            PrivilegedAction(
                name="storage.safety-check",
                description="Validate the configured storage marker and read/write behavior.",
            ),
            PrivilegedAction(
                name="storage.managed-drive",
                description="Format, mount, or update the explicitly managed backup drive.",
            ),
            PrivilegedAction(
                name="storage.mount",
                description="Mount the configured managed backup drive from the dashboard.",
            ),
            PrivilegedAction(
                name="storage.mount-check",
                description="Run the scheduled managed-drive mount check through the worker.",
            ),
            PrivilegedAction(
                name="storage.managed-unmount",
                description="Unmount the configured managed backup drive from the dashboard.",
            ),
            PrivilegedAction(
                name="storage.format",
                description="Erase a setup-selected disk and create one NTFS backup partition.",
            ),
            PrivilegedAction(
                name="storage.unmount",
                description="Temporarily unmount setup-selected disks or partitions.",
            ),
            PrivilegedAction(
                name="system.reboot",
                description="Restart the host from the dashboard power control.",
            ),
            PrivilegedAction(
                name="system.poweroff",
                description="Shut down the host from the dashboard power control.",
            ),
        ),
        plan_changes=(
            PlanChange(
                title="Default to an existing folder",
                detail="Managed-drive setup stays explicit so SSS does not own a mount by accident.",
            ),
            PlanChange(
                title="Record exact storage writes",
                detail=(
                    "Record the marker file after storage is prepared, and record the fstab "
                    "entry only after managed-drive setup writes it."
                ),
            ),
        ),
    )
