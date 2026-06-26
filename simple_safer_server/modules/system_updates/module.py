from __future__ import annotations

from simple_safer_server.core.module_contract import (
    HelpEntry,
    ModuleHelp,
    ModuleNavItem,
    ModuleRoute,
    ModuleState,
    SssModule,
)


def create_module() -> SssModule:
    return SssModule(
        slug="system-updates",
        title="System Updates",
        description="Shows operating system update state.",
        state=ModuleState.READ_ONLY,
        routes=(
            ModuleRoute(
                rule="/system_updates",
                endpoint="system_updates_routes.system_updates_page",
                page=True,
            ),
            ModuleRoute(
                rule="/api/system_updates/summary",
                endpoint="system_updates_routes.api_system_updates_summary",
            ),
            ModuleRoute(
                rule="/api/system_updates/status",
                endpoint="system_updates_routes.api_system_updates_status",
            ),
            ModuleRoute(
                rule="/api/system_updates/application/refresh",
                endpoint="system_updates_routes.api_system_updates_application_refresh",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/system_updates/application/update",
                endpoint="system_updates_routes.api_system_updates_application_update",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/system_updates/<operation>/start",
                endpoint="system_updates_routes.api_system_updates_start",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/system_updates/stop",
                endpoint="system_updates_routes.api_system_updates_stop",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/system_updates/settings",
                endpoint="system_updates_routes.api_system_updates_save_settings",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/system_updates/remove_stale_locks",
                endpoint="system_updates_routes.api_system_updates_remove_stale_locks",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/system_updates/livepatch/setup",
                endpoint="system_updates_routes.api_system_updates_livepatch_setup",
                methods=("POST",),
            ),
        ),
        nav_items=(
            ModuleNavItem(
                label="System Updates",
                endpoint="system_updates_routes.system_updates_page",
                icon="fas fa-download fa-fw",
                order=75,
            ),
        ),
        help=ModuleHelp(
            purpose="System Updates shows OS update state without owning OS update policy.",
            setup_intro="Keep this module read-only unless OS update ownership becomes explicit and narrow.",
            docs_path="docs/system_updates.md",
            field_help=(
                HelpEntry(
                    key="automatic_updates",
                    text="These values show the operating system policy. Change OS update policy outside SSS.",
                ),
            ),
            empty_states=(
                HelpEntry(
                    key="status_unavailable",
                    text="SSS could not read the operating system update status.",
                ),
            ),
            recovery_actions=(
                HelpEntry(
                    key="status_unavailable",
                    text="Check apt and system logs on the server, then refresh this page.",
                ),
            ),
        ),
        plan_warnings=(
            "Do not manage unattended-upgrades by default.",
            "Remove this module if it cannot keep a clean ownership boundary.",
        ),
    )
