import csv
from dataclasses import dataclass
from typing import Any

CONFIG_SECTION = "system"
CONFIG_KEY = "disabled_features"


@dataclass(frozen=True)
class Feature:
    """A top-level Web UI feature that can be hidden from operators."""

    key: str
    label: str
    icon: str
    endpoint: str
    aliases: tuple[str, ...] = ()


NAV_FEATURES = (
    Feature("overview", "Overview", "fas fa-house fa-fw", "task_routes.dashboard"),
    Feature(
        "file_sharing",
        "File Sharing",
        "fas fa-share-nodes fa-fw",
        "network_file_sharing",
        aliases=("network_file_sharing", "sharing", "smb", "samba"),
    ),
    Feature("users", "Users", "fas fa-users fa-fw", "users_routes.users_page"),
    Feature(
        "drive_health",
        "Drive Health",
        "fas fa-hard-drive fa-fw",
        "drive_health_routes.drives",
        aliases=("drives", "health", "hdsentinel"),
    ),
    Feature("ddns", "DDNS", "fas fa-globe fa-fw", "ddns_routes.ddns_page"),
    Feature(
        "cloud_backup",
        "Cloud Backup",
        "fas fa-cloud-arrow-up fa-fw",
        "cloud_backup_routes.cloud_backup_page",
        aliases=("backup", "cloud"),
    ),
    Feature(
        "system_updates",
        "System Updates",
        "fas fa-download fa-fw",
        "system_updates_routes.system_updates_page",
        aliases=("updates", "app_update", "application_update"),
    ),
    Feature("alerts", "Alerts", "fas fa-bell fa-fw", "alerts_routes.alerts_page"),
)

FEATURES_BY_KEY = {feature.key: feature for feature in NAV_FEATURES}
FEATURE_ALIASES = {
    alias: feature.key for feature in NAV_FEATURES for alias in (feature.key, *feature.aliases)
}

ENDPOINT_FEATURES = {
    "network_file_sharing": "file_sharing",
    "task_routes.dashboard": "overview",
    "task_routes.api_tasks_schedule": "overview",
    "storage_routes.unmount": "overview",
    "storage_routes.restart": "overview",
    "storage_routes.shutdown": "overview",
    "storage_routes.api_storage_status": "overview",
    "storage_routes.dashboard_mount_drive": "overview",
    "storage_routes.api_system_resources": "overview",
    "storage_routes.api_backup_drive_drives": "drive_health",
    "storage_routes.api_backup_drive_unmount": "drive_health",
    "storage_routes.api_backup_drive_configure": "drive_health",
}

ENDPOINT_PREFIX_FEATURES = (
    ("smb_routes.", "file_sharing"),
    ("users_routes.", "users"),
    ("drive_health_routes.", "drive_health"),
    ("ddns_routes.", "ddns"),
    ("cloud_backup_routes.", "cloud_backup"),
    ("system_updates_routes.", "system_updates"),
    ("alerts_routes.", "alerts"),
)

TASK_FEATURES = {
    "Check Mount": "overview",
    "Drive Health Check": "drive_health",
    "Cloud Backup": "cloud_backup",
    "DDNS Update": "ddns",
    "App Update": "system_updates",
}

TASK_ENDPOINTS = {
    "task_routes.task_detail",
    "task_routes.task_logs",
    "task_routes.api_task_status",
    "task_routes.start_task",
    "task_routes.stop_task",
    "task_routes.disable_schedule",
    "task_routes.enable_schedule",
}


def normalize_feature_token(value: str) -> str:
    """Normalize config tokens so admins can use common CSV spellings."""
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def parse_disabled_features(value: str | None) -> set[str]:
    if not value:
        return set()
    try:
        tokens = next(csv.reader([value], skipinitialspace=True), [])
    except csv.Error:
        tokens = value.split(",")
    return {
        FEATURE_ALIASES[token]
        for token in (normalize_feature_token(item) for item in tokens)
        if token in FEATURE_ALIASES
    }


class FeatureManager:
    """Reads the admin-managed feature visibility list from config.conf."""

    def __init__(self, config_manager: Any):
        self.config_manager = config_manager

    def disabled_feature_keys(self) -> set[str]:
        # The config file is often edited by hand, so each request should see a
        # fresh CSV list without needing a service restart.
        self.config_manager.load_config()
        return parse_disabled_features(
            self.config_manager.get_value(CONFIG_SECTION, CONFIG_KEY, "")
        )

    def is_feature_disabled(self, feature_key: str) -> bool:
        return feature_key in self.disabled_feature_keys()

    def visible_nav_features(self) -> list[Feature]:
        disabled = self.disabled_feature_keys()
        return [feature for feature in NAV_FEATURES if feature.key not in disabled]

    def feature_label(self, feature_key: str) -> str:
        feature = FEATURES_BY_KEY.get(feature_key)
        if feature is None:
            return feature_key.replace("_", " ").title()
        return feature.label

    def feature_for_endpoint(
        self, endpoint: str | None, view_args: dict[str, Any] | None
    ) -> str | None:
        if endpoint in TASK_ENDPOINTS:
            task_name = (view_args or {}).get("task_name")
            if isinstance(task_name, str):
                return TASK_FEATURES.get(task_name)
            return None
        if endpoint in ENDPOINT_FEATURES:
            return ENDPOINT_FEATURES[endpoint]
        if endpoint:
            for prefix, feature_key in ENDPOINT_PREFIX_FEATURES:
                if endpoint.startswith(prefix):
                    return feature_key
        return None

    def first_visible_endpoint(self) -> str | None:
        visible = self.visible_nav_features()
        if not visible:
            return None
        return visible[0].endpoint

    def filter_task_summaries(self, summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        disabled = self.disabled_feature_keys()
        return [
            summary
            for summary in summaries
            if TASK_FEATURES.get(str(summary.get("name"))) not in disabled
        ]
