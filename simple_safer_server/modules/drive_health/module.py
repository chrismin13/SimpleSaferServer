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
        slug="drive-health",
        title="Drive Health",
        description="Reports disk health from available host tools.",
        state=ModuleState.ACTIVE,
        routes=(
            ModuleRoute(
                rule="/drives",
                endpoint="drive_health_routes.drives",
                methods=("GET", "POST"),
                page=True,
            ),
            ModuleRoute(
                rule="/api/drive_health/summary",
                endpoint="drive_health_routes.api_drive_health_summary",
            ),
            ModuleRoute(
                rule="/api/drive_health/refresh",
                endpoint="drive_health_routes.api_drive_health_refresh",
                methods=("POST",),
            ),
        ),
        nav_items=(
            ModuleNavItem(
                label="Drive Health",
                endpoint="drive_health_routes.drives",
                icon="fas fa-hard-drive fa-fw",
                order=50,
            ),
        ),
        jobs=(
            JobDefinition(
                name="drive-health",
                module_slug="drive-health",
                title="Drive Health",
                description="Checks disk health and records alerts when needed.",
                task_name="Drive Health Check",
                daily_time_config_section="schedule",
                daily_time_config_key="backup_cloud_time",
                default_daily_time="03:00",
                daily_time_offset_minutes=-2,
            ),
        ),
        help=ModuleHelp(
            purpose="Drive Health helps spot storage problems before backups are lost.",
            setup_intro=(
                "Detect available health tools instead of installing every backend by default."
            ),
            docs_path="docs/drive_health.md",
            field_help=(
                HelpEntry(
                    key="health_change_alert",
                    text="Send an alert when a drive health result becomes worse than the previous result.",
                ),
            ),
            empty_states=(
                HelpEntry(
                    key="no_backend",
                    text="No drive health backend is available yet. Install smartmontools or HDSentinel if you want health details.",
                ),
            ),
            error_explanations=(
                HelpEntry(
                    key="backend_failed",
                    text="The health tool ran but did not return usable drive health data.",
                ),
            ),
            recovery_actions=(
                HelpEntry(
                    key="backend_failed",
                    text="Check that the drive is visible to the operating system and that the selected health tool supports it.",
                ),
            ),
        ),
        required_tools=(
            RequiredTool(
                name="smartctl",
                purpose="Reads SMART health data when smartmontools is installed.",
                optional=True,
            ),
            RequiredTool(
                name="hdsentinel",
                purpose="Reads HDSentinel health data when the optional binary is installed.",
                optional=True,
            ),
        ),
        privileged_actions=(
            PrivilegedAction(
                name="drive-health.page-check",
                description="Run an explicit SMART/HDSentinel probe for the Drive Health page.",
            ),
            PrivilegedAction(
                name="drive-health.refresh-summary",
                description="Run an explicit SMART/HDSentinel probe for the Dashboard health summary.",
            ),
            PrivilegedAction(
                name="drive-health.scheduled-check",
                description="Run the scheduled drive health worker check with root-only probe access.",
            ),
        ),
        owned_resources=(
            OwnedResource(
                kind="config-section",
                identifier="<config>/config.conf[hdsentinel]",
                reason="Store drive-health alert settings in SSS config.",
            ),
            OwnedResource(
                kind="state-file",
                identifier="<data>/hdsentinel_state.json",
                reason="Remember previous drive-health readings for change alerts.",
            ),
        ),
        plan_changes=(
            PlanChange(
                title="Detect available health tools",
                detail=(
                    "Use smartctl or HDSentinel only when the tool is already installed, "
                    "instead of installing every drive-health backend by default."
                ),
            ),
            PlanChange(
                title="Record drive-health state",
                detail=(
                    "Store HDSentinel settings and the previous health reading so scheduled "
                    "checks can alert when a drive gets worse."
                ),
            ),
        ),
        plan_warnings=(
            "Explicit health checks may wake disks because the operating system has to query the drive.",
        ),
    )
