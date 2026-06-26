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
    return SssModule(
        slug="alerts",
        title="Alerts",
        description="Sends backup and system warnings to the administrator.",
        state=ModuleState.ACTIVE,
        routes=(
            ModuleRoute(rule="/alerts", endpoint="alerts_routes.alerts_page", page=True),
            ModuleRoute(
                rule="/api/alerts/generate-test",
                endpoint="alerts_routes.api_generate_test_alerts",
                methods=("POST",),
            ),
            ModuleRoute(rule="/api/alerts", endpoint="alerts_routes.api_get_alerts"),
            ModuleRoute(
                rule="/api/alerts/<int:alert_id>",
                endpoint="alerts_routes.api_get_alert",
            ),
            ModuleRoute(
                rule="/api/alerts/<int:alert_id>/mark-read",
                endpoint="alerts_routes.api_mark_alert_read",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/alerts/clear",
                endpoint="alerts_routes.api_clear_alerts",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/alerts/mark-all-read",
                endpoint="alerts_routes.api_mark_all_alerts_read",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/alerts/email-config",
                endpoint="alerts_routes.api_get_email_config",
            ),
            ModuleRoute(
                rule="/api/alerts/email-config",
                endpoint="alerts_routes.api_set_email_config",
                methods=("POST",),
            ),
        ),
        nav_items=(
            ModuleNavItem(
                label="Alerts",
                endpoint="alerts_routes.alerts_page",
                icon="fas fa-bell fa-fw",
                order=80,
            ),
        ),
        help=ModuleHelp(
            purpose="Alerts tell you when backups or storage checks fail.",
            setup_intro="Configure email alerts so backup failures are not silent.",
            warnings=(
                "Without alerts, backup failures may go unnoticed until you check the dashboard.",
            ),
            docs_path="docs/alerts.md",
            field_help=(
                HelpEntry(
                    key="email_address",
                    text="Where SSS sends backup, storage, and health warnings.",
                ),
                HelpEntry(
                    key="from_address",
                    text="The sender address shown by alert emails.",
                ),
                HelpEntry(
                    key="smtp_server",
                    text="The mail server SSS signs in to when sending alerts.",
                ),
                HelpEntry(
                    key="smtp_port",
                    text="Usually 587 for STARTTLS or 465 for SMTP over TLS.",
                ),
                HelpEntry(
                    key="smtp_username",
                    text="The username for the mail account that sends alerts.",
                ),
                HelpEntry(
                    key="smtp_password",
                    text="Use an app password when your mail provider supports one.",
                ),
            ),
            success_messages=(
                HelpEntry(
                    key="config_saved",
                    text="Alert settings saved. Send a test alert before relying on them.",
                ),
            ),
            error_explanations=(
                HelpEntry(
                    key="smtp_failed",
                    text="SSS could not send mail with the saved SMTP settings.",
                ),
            ),
            recovery_actions=(
                HelpEntry(
                    key="smtp_failed",
                    text="Check the server, port, username, password, and whether your mail provider requires an app password.",
                ),
            ),
        ),
        owned_resources=(
            OwnedResource(
                kind="config-file",
                identifier="<config>/smtp.conf",
                reason="Store the SSS-owned SMTP settings used for alert email.",
            ),
            OwnedResource(
                kind="state-file",
                identifier="<config>/alerts.json",
                reason="Store local alert history shown in the Web UI.",
            ),
        ),
        required_tools=(
            RequiredTool(
                name="update-ca-certificates",
                purpose="Maintains the system CA bundle used for SMTP TLS verification.",
            ),
        ),
        privileged_actions=(
            PrivilegedAction(
                name="alerts.write-smtp-config",
                description="Write the SSS-owned SMTP config from a JSON payload passed on stdin.",
            ),
        ),
        plan_changes=(
            PlanChange(
                title="Use Python SMTP",
                detail="Alerts use SSS-owned SMTP config and Python SMTP instead of requiring msmtp.",
            ),
        ),
    )
