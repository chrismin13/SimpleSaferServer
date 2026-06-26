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
    """Return the Cloud Backup module contract used by the CLI and future UI."""
    return SssModule(
        slug="cloud-backup",
        title="Cloud Backup",
        description="Copies the configured storage folder to a cloud destination.",
        state=ModuleState.ACTIVE,
        routes=(
            ModuleRoute(
                rule="/cloud_backup",
                endpoint="cloud_backup_routes.cloud_backup_page",
                page=True,
            ),
            ModuleRoute(
                rule="/api/cloud_backup/config",
                endpoint="cloud_backup_routes.api_cloud_backup_get_config",
            ),
            ModuleRoute(
                rule="/api/cloud_backup/config",
                endpoint="cloud_backup_routes.api_cloud_backup_set_config",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/cloud_backup/status",
                endpoint="cloud_backup_routes.api_cloud_backup_status",
            ),
            ModuleRoute(
                rule="/api/cloud_backup/run",
                endpoint="cloud_backup_routes.api_cloud_backup_run",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/cloud_backup/mega/list_folders",
                endpoint="cloud_backup_routes.api_cloud_backup_mega_list_folders",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/cloud_backup/mega/create_folder",
                endpoint="cloud_backup_routes.api_cloud_backup_mega_create_folder",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/cloud_backup/schedule",
                endpoint="cloud_backup_routes.api_cloud_backup_get_schedule",
            ),
            ModuleRoute(
                rule="/api/cloud_backup/schedule",
                endpoint="cloud_backup_routes.api_cloud_backup_set_schedule",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/cloud_backup/mega/validate",
                endpoint="cloud_backup_routes.api_cloud_backup_mega_validate",
                methods=("POST",),
            ),
        ),
        nav_items=(
            ModuleNavItem(
                label="Cloud Backup",
                endpoint="cloud_backup_routes.cloud_backup_page",
                icon="fas fa-cloud-arrow-up fa-fw",
                order=70,
            ),
        ),
        jobs=(
            JobDefinition(
                name="cloud-backup",
                module_slug="cloud-backup",
                title="Cloud Backup",
                description="Runs storage safety checks and syncs to the configured cloud target.",
                task_name="Cloud Backup",
                daily_time_config_section="schedule",
                daily_time_config_key="backup_cloud_time",
                default_daily_time="03:00",
                enabled_config_section="backup",
                enabled_config_key="cloud_enabled",
            ),
        ),
        help=ModuleHelp(
            purpose="Cloud Backup gives the server an off-site copy of backup data.",
            setup_intro="Configure rclone with an SSS-owned config before any cloud sync runs.",
            warnings=(
                "Cloud sync can delete remote files when the local source is wrong, so storage safety checks must pass first.",
            ),
            docs_path="docs/cloud_backup.md",
            field_help=(
                HelpEntry(
                    key="backup_time",
                    text="The daily time when the worker should run the cloud backup.",
                ),
                HelpEntry(
                    key="remote_name",
                    text="The rclone remote and folder that receive the cloud backup.",
                ),
                HelpEntry(
                    key="bandwidth_limit",
                    text="Optional speed limit for cloud uploads, useful on slow connections.",
                ),
                HelpEntry(
                    key="mega_email",
                    text="The MEGA account SSS signs in to when creating the rclone config.",
                ),
                HelpEntry(
                    key="mega_password",
                    text="SSS stores the generated rclone config, not this password.",
                ),
                HelpEntry(
                    key="mega_folder",
                    text="Choose a folder used only for this server's cloud backup.",
                ),
                HelpEntry(
                    key="rclone_config",
                    text="Paste a complete rclone config. SSS stores it in its own config path.",
                ),
            ),
            confirmations=(
                HelpEntry(
                    key="run_sync",
                    text="Run cloud backup only after the storage safety check passes.",
                ),
            ),
            empty_states=(
                HelpEntry(
                    key="not_configured",
                    text="Cloud backup is not protecting this server until a destination is configured.",
                ),
            ),
            error_explanations=(
                HelpEntry(
                    key="storage_check_failed",
                    text="Cloud backup stopped because the local storage folder could not be trusted.",
                ),
            ),
            recovery_actions=(
                HelpEntry(
                    key="storage_check_failed",
                    text="Open Storage, repair the marker or mount, then run the safety check again.",
                ),
            ),
        ),
        required_tools=(
            RequiredTool(
                name="update-ca-certificates",
                purpose="Maintains the system CA bundle used by outbound HTTPS connections.",
            ),
            RequiredTool(
                name="rclone",
                purpose="Runs the cloud sync after storage safety checks pass.",
            ),
        ),
        owned_resources=(
            OwnedResource(
                kind="config-file",
                identifier="/etc/SimpleSaferServer/rclone/rclone.conf",
                reason="Keep SSS cloud backup separate from root's global rclone config.",
            ),
        ),
        privileged_actions=(
            PrivilegedAction(
                name="cloud-backup.write-rclone-config",
                description="Write the SSS-owned rclone config without touching root's global rclone config.",
            ),
            PrivilegedAction(
                name="cloud-backup.sync",
                description="Run rclone with the SSS-owned config and configured storage path.",
            ),
        ),
        plan_changes=(
            PlanChange(
                title="Isolate rclone config",
                detail="Use only the SSS-owned rclone config path and pass it explicitly to rclone.",
                requires_privilege=True,
            ),
            PlanChange(
                title="Register worker job",
                detail="Run scheduled cloud backups through the SSS worker instead of a generated systemd timer.",
            ),
        ),
    )
