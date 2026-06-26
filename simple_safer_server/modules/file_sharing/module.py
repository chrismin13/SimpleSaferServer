from __future__ import annotations

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
    """Return the File Sharing module contract used by CLI and setup planning."""
    return SssModule(
        slug="file-sharing",
        title="File Sharing",
        description="Manages SSS-owned Samba shares without owning all Samba config.",
        state=ModuleState.ACTIVE,
        routes=(
            ModuleRoute(
                rule="/network_file_sharing",
                endpoint="smb_routes.network_file_sharing",
                page=True,
            ),
            ModuleRoute(rule="/api/smb/shares", endpoint="smb_routes.api_list_smb_shares"),
            ModuleRoute(
                rule="/api/smb/shares",
                endpoint="smb_routes.api_add_smb_share",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/smb/shares/<share_name>",
                endpoint="smb_routes.api_edit_smb_share",
                methods=("PUT",),
            ),
            ModuleRoute(
                rule="/api/smb/shares/<share_name>",
                endpoint="smb_routes.api_delete_smb_share",
                methods=("DELETE",),
            ),
            ModuleRoute(rule="/api/smb/status", endpoint="smb_routes.api_smb_status"),
            ModuleRoute(
                rule="/api/smb/restart",
                endpoint="smb_routes.api_restart_smb",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/smb/shares/<share_name>/users",
                endpoint="smb_routes.api_get_share_users",
            ),
            ModuleRoute(
                rule="/api/smb/shares/<share_name>/users",
                endpoint="smb_routes.api_update_share_users",
                methods=("PUT",),
            ),
            ModuleRoute(
                rule="/api/list_dirs",
                endpoint="smb_routes.api_list_dirs",
                methods=("GET", "POST"),
            ),
        ),
        nav_items=(
            ModuleNavItem(
                label="File Sharing",
                endpoint="smb_routes.network_file_sharing",
                icon="fas fa-share-nodes fa-fw",
                order=20,
            ),
        ),
        help=ModuleHelp(
            purpose="File Sharing exposes selected backup folders on the local network.",
            setup_intro=(
                "Enable Samba management only after showing exactly which SSS-owned files "
                "will be added."
            ),
            warnings=(
                "Restarting Samba can disconnect active file copies.",
            ),
            docs_path="docs/network_file_sharing.md",
            field_help=(
                HelpEntry(
                    key="server_name",
                    text="The network name people use to find this server. Alert emails use it too.",
                ),
                HelpEntry(
                    key="share_name",
                    text="Use letters, numbers, hyphens, and underscores so Samba clients can open the share reliably.",
                ),
                HelpEntry(
                    key="share_path",
                    text="Choose the local folder that network users should see.",
                ),
                HelpEntry(
                    key="share_comment",
                    text="Optional description shown beside the share in this UI.",
                ),
                HelpEntry(
                    key="writable",
                    text="When enabled, allowed users can create, change, and delete files in this share.",
                ),
                HelpEntry(
                    key="valid_users",
                    text="Limit write access to the users who should be able to copy files here.",
                ),
            ),
            confirmations=(
                HelpEntry(
                    key="reload_samba",
                    text="Reload Samba after saving shares. Active network copies may disconnect.",
                ),
            ),
            empty_states=(
                HelpEntry(
                    key="no_shares",
                    text="No SSS-managed shares exist yet.",
                ),
            ),
            error_explanations=(
                HelpEntry(
                    key="unmanaged_conflict",
                    text="A Samba share with this name already exists outside SSS-managed files.",
                ),
            ),
            recovery_actions=(
                HelpEntry(
                    key="unmanaged_conflict",
                    text="Rename or remove the unmanaged Samba share, then add it through SSS if you want SSS to manage it.",
                ),
            ),
        ),
        required_tools=(
            RequiredTool(name="smbd", purpose="Serves SMB file shares."),
            RequiredTool(
                name="nmbd",
                purpose="Provides NetBIOS discovery for older Windows network browsing.",
                optional=True,
            ),
            RequiredTool(
                name="wsdd2",
                purpose="Provides modern Windows network discovery when available.",
                optional=True,
            ),
        ),
        owned_resources=(
            OwnedResource(
                kind="module-state",
                identifier="<data>/ownership.json[file-sharing-applied]",
                reason="Remember that File Sharing setup was accepted before Samba writes are allowed.",
            ),
            OwnedResource(
                kind="config-file",
                identifier="/etc/samba/simple_safer_server_globals.conf",
                reason="Store SSS-owned Samba global settings separately.",
                record_on_apply=False,
            ),
            OwnedResource(
                kind="config-file",
                identifier="/etc/samba/simple_safer_server_shares.conf",
                reason="Store only SSS-managed share sections.",
                record_on_apply=False,
            ),
        ),
        privileged_actions=(
            PrivilegedAction(
                name="file-sharing.reload",
                description="Validate and reload or restart Samba after SSS-owned config changes.",
            ),
            PrivilegedAction(
                name="file-sharing.remove-user",
                description="Remove a Samba account when an SSS user is deleted.",
            ),
            PrivilegedAction(
                name="file-sharing.sync-user",
                description="Create or update a File Sharing-owned Samba account for an SSS user.",
            ),
            PrivilegedAction(
                name="file-sharing.write-shares",
                description="Publish SSS-owned Samba include files and validate the effective Samba config.",
            ),
        ),
        plan_changes=(
            PlanChange(
                title="Keep Samba ownership narrow",
                detail="Write only SSS-owned include files and leave smb.conf as the admin-owned entrypoint.",
                requires_privilege=True,
            ),
            PlanChange(
                title="Preserve unmanaged shares",
                detail="Detect existing non-system shares and refuse to overwrite them automatically.",
            ),
        ),
    )
