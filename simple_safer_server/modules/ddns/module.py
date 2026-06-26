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
    """Return the DDNS module contract used by the CLI and future UI."""
    return SssModule(
        slug="ddns",
        title="DDNS",
        description="Updates dynamic DNS providers from saved SSS config.",
        state=ModuleState.ACTIVE,
        routes=(
            ModuleRoute(rule="/ddns", endpoint="ddns_routes.ddns_page", page=True),
            ModuleRoute(rule="/api/ddns/config", endpoint="ddns_routes.get_ddns_config"),
            ModuleRoute(
                rule="/api/ddns/config",
                endpoint="ddns_routes.save_ddns_config",
                methods=("POST",),
            ),
            ModuleRoute(
                rule="/api/ddns/run",
                endpoint="ddns_routes.run_ddns_manual",
                methods=("POST",),
            ),
        ),
        nav_items=(
            ModuleNavItem(
                label="DDNS",
                endpoint="ddns_routes.ddns_page",
                icon="fas fa-globe fa-fw",
                order=60,
                admin_only=True,
            ),
        ),
        jobs=(
            JobDefinition(
                name="ddns-update",
                module_slug="ddns",
                title="DDNS Update",
                description="Updates the configured dynamic DNS provider.",
                task_name="DDNS Update",
                interval_seconds=300,
            ),
        ),
        help=ModuleHelp(
            purpose="DDNS keeps a hostname pointed at the server's current public IP address.",
            setup_intro=(
                "DDNS stores provider settings in SSS config and runs updates through the "
                "shared job interface."
            ),
            warnings=(
                "Fake mode does not sandbox provider APIs. Valid DDNS credentials can update live DNS records.",
            ),
            docs_path="docs/ddns.md",
            field_help=(
                HelpEntry(
                    key="provider",
                    text="Choose the DNS provider that owns the hostname you want to update.",
                ),
                HelpEntry(
                    key="duckdns_enabled",
                    text="Automatically update your DuckDNS hostname from the SSS worker.",
                ),
                HelpEntry(
                    key="duckdns_domain",
                    text="Enter only the DuckDNS subdomain. SSS adds .duckdns.org for you.",
                ),
                HelpEntry(
                    key="duckdns_token",
                    text="Copy the token from the DuckDNS dashboard for the account that owns this hostname.",
                ),
                HelpEntry(
                    key="cloudflare_enabled",
                    text="Automatically keep one Cloudflare A record pointed at this server's public IPv4 address.",
                ),
                HelpEntry(
                    key="cloudflare_zone_id",
                    text="Use the Zone ID from the Cloudflare domain overview page.",
                ),
                HelpEntry(
                    key="cloudflare_token",
                    text="Use a scoped Cloudflare API token that can edit DNS records for this zone.",
                ),
                HelpEntry(
                    key="cloudflare_record_name",
                    text="Use the full DNS record name that should point at this server, such as server.example.com.",
                ),
                HelpEntry(
                    key="cloudflare_proxy",
                    text=(
                        "Leave proxying off for normal DNS, SSH, VPNs, game servers, and custom ports. "
                        "Turn it on only for Cloudflare-supported web traffic."
                    ),
                ),
                HelpEntry(
                    key="token",
                    text="Use a provider token with only the permissions needed to update this DNS record.",
                ),
            ),
            empty_states=(
                HelpEntry(
                    key="not_configured",
                    text="DDNS is idle until a provider and hostname are configured.",
                ),
            ),
            success_messages=(
                HelpEntry(
                    key="update_sent",
                    text="DDNS update sent. DNS changes can still take time to appear everywhere.",
                ),
            ),
            error_explanations=(
                HelpEntry(
                    key="provider_rejected",
                    text="The DNS provider rejected the update request.",
                ),
            ),
            recovery_actions=(
                HelpEntry(
                    key="provider_rejected",
                    text="Check the token, zone, record name, and whether the provider account can edit this record.",
                ),
            ),
        ),
        privileged_actions=(
            PrivilegedAction(
                name="ddns.update",
                description="Run the configured DDNS provider update.",
            ),
        ),
        required_tools=(
            RequiredTool(
                name="update-ca-certificates",
                purpose="Maintains the system CA bundle used by DDNS provider HTTPS requests.",
            ),
        ),
        owned_resources=(
            OwnedResource(
                kind="config-section",
                identifier="<config>/config.conf[ddns]",
                reason="Store DDNS provider settings without editing host DNS config.",
            ),
            OwnedResource(
                kind="config-secret",
                identifier="<config>/.secrets[duckdns_token,cloudflare_token]",
                reason="Store provider tokens in the SSS encrypted secrets file.",
            ),
        ),
        plan_changes=(
            PlanChange(
                title="Use module-owned DDNS behavior",
                detail="Keep DDNS route, service, setup plan, help text, and jobs together in one module.",
            ),
            PlanChange(
                title="Register worker job",
                detail="Run scheduled DDNS updates through the SSS worker instead of a generated systemd timer.",
            ),
        ),
    )
