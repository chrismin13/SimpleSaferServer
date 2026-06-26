from pathlib import Path

import pytest
from flask import Flask

from simple_safer_server.core.builtin_modules import create_builtin_module_registry
from simple_safer_server.core.module_checks import check_module_requirements
from simple_safer_server.core.module_contract import (
    HelpEntry,
    ModuleHelp,
    ModuleNavItem,
    ModuleRegistry,
    ModuleRoute,
    ModuleState,
    RequiredTool,
    SssModule,
)
from simple_safer_server.core.module_serialization import module_data, module_plan_data
from simple_safer_server.core.privileged_actions import create_builtin_privileged_action_registry
from simple_safer_server.modules import module_blueprints


def test_builtin_registry_has_expected_module_slugs():
    registry = create_builtin_module_registry()

    assert [module.slug for module in registry.list_modules()] == [
        "alerts",
        "cloud-backup",
        "ddns",
        "drive-health",
        "file-sharing",
        "storage",
        "system-updates",
    ]


def test_module_blueprints_are_registered_from_module_package():
    assert [blueprint.name for blueprint in module_blueprints()] == [
        "ddns_routes",
        "cloud_backup_routes",
        "system_updates_routes",
        "alerts_routes",
        "smb_routes",
        "storage_routes",
        "drive_health_routes",
    ]


def test_cloud_backup_plan_declares_rclone_config_ownership():
    registry = create_builtin_module_registry()

    plan = registry.module_for_slug("cloud-backup").build_plan()

    assert any(tool.name == "update-ca-certificates" for tool in plan.required_tools)
    assert any(tool.name == "rclone" for tool in plan.required_tools)
    assert any(
        resource.identifier == "/etc/SimpleSaferServer/rclone/rclone.conf"
        for resource in plan.owned_resources
    )
    assert any(action.name == "cloud-backup.write-rclone-config" for action in plan.privileged_actions)
    assert any(action.name == "cloud-backup.sync" for action in plan.privileged_actions)


def test_ddns_plan_is_owned_by_deep_module():
    registry = create_builtin_module_registry()

    plan = registry.module_for_slug("ddns").build_plan()

    assert plan.module_slug == "ddns"
    assert any(tool.name == "update-ca-certificates" for tool in plan.required_tools)
    assert any(change.title == "Use module-owned DDNS behavior" for change in plan.changes)
    assert any(action.name == "ddns.update" for action in plan.privileged_actions)
    assert any("Fake mode" in warning for warning in plan.warnings)


def test_alerts_plan_declares_smtp_helper_action():
    registry = create_builtin_module_registry()

    plan = registry.module_for_slug("alerts").build_plan()

    assert any(tool.name == "update-ca-certificates" for tool in plan.required_tools)
    assert any(action.name == "alerts.write-smtp-config" for action in plan.privileged_actions)
    assert any(resource.identifier == "<config>/smtp.conf" for resource in plan.owned_resources)


def test_storage_plan_declares_optional_managed_drive_tools():
    registry = create_builtin_module_registry()

    plan = registry.module_for_slug("storage").build_plan()
    tools = {tool.name: tool for tool in plan.required_tools}

    for tool_name in ("lsblk", "blkid", "sfdisk", "mkfs.ntfs", "ntfs-3g"):
        assert tools[tool_name].optional is True
    resource_flags = {resource.identifier: resource.record_on_apply for resource in plan.owned_resources}
    assert resource_flags["<config>/config.conf[storage]"] is True
    assert resource_flags["<storage>/.simple-safer-server/storage.json"] is False
    assert resource_flags["/etc/fstab#SimpleSaferServer managed backup drive"] is False


def test_storage_missing_managed_drive_tools_do_not_block_existing_folder_setup():
    registry = create_builtin_module_registry()

    check = check_module_requirements(
        registry.module_for_slug("storage"),
        tool_finder=lambda _name: None,
    )

    assert check.blocking is False


def test_file_sharing_plan_declares_only_smbd_as_blocking_tool():
    registry = create_builtin_module_registry()

    plan = registry.module_for_slug("file-sharing").build_plan()
    tools = {tool.name: tool for tool in plan.required_tools}

    assert tools["smbd"].optional is False
    assert tools["nmbd"].optional is True
    assert tools["wsdd2"].optional is True

    check = check_module_requirements(
        registry.module_for_slug("file-sharing"),
        tool_finder=lambda _name: None,
    )

    assert check.blocking is True
    assert [tool_check.tool.name for tool_check in check.required_tools if tool_check.blocking] == [
        "smbd"
    ]
    resource_flags = {resource.identifier: resource.record_on_apply for resource in plan.owned_resources}
    assert resource_flags["<data>/ownership.json[file-sharing-applied]"] is True
    assert resource_flags["/etc/samba/simple_safer_server_globals.conf"] is False
    assert resource_flags["/etc/samba/simple_safer_server_shares.conf"] is False


def test_registry_rejects_duplicate_module_slugs():
    module = SssModule(
        slug="duplicate",
        title="Duplicate",
        description="Duplicate module.",
        state=ModuleState.PLANNED,
        help=ModuleHelp(purpose="Exercise duplicate detection."),
    )

    with pytest.raises(ValueError, match="unique"):
        ModuleRegistry((module, module))


def test_module_requirement_check_reports_blocking_missing_tools():
    module = SssModule(
        slug="needs-tool",
        title="Needs Tool",
        description="Exercise tool checks.",
        state=ModuleState.OPTIONAL,
        help=ModuleHelp(purpose="Exercise tool checks."),
        required_tools=(
            RequiredTool(name="required-tool", purpose="Required."),
            RequiredTool(name="optional-tool", purpose="Optional.", optional=True),
        ),
    )

    check = check_module_requirements(module, tool_finder=lambda name: None)

    assert check.summary == "Required tools are missing."
    assert check.blocking is True
    assert [tool_check.blocking for tool_check in check.required_tools] == [True, False]


def test_builtin_modules_expose_docs_and_structured_ui_help():
    registry = create_builtin_module_registry()
    repo_root = Path(__file__).resolve().parents[1]
    index_html = (repo_root / "index.html").read_text(encoding="utf-8")

    for module in registry.list_modules():
        assert module.help.docs_path.startswith("docs/"), module.slug
        assert (repo_root / module.help.docs_path).is_file(), module.slug
        assert module.help.docs_path in index_html, module.slug
        assert module.help.purpose, module.slug
        help_entries = (
            module.help.field_help
            + module.help.tooltips
            + module.help.empty_states
            + module.help.confirmations
            + module.help.success_messages
            + module.help.error_explanations
            + module.help.recovery_actions
        )
        assert help_entries, module.slug
        assert all(isinstance(entry, HelpEntry) for entry in help_entries)
        assert all(entry.key and entry.text for entry in help_entries)


def test_active_modules_explain_their_setup_plan_changes():
    registry = create_builtin_module_registry()

    for module in registry.list_modules():
        if module.state == ModuleState.ACTIVE:
            plan = module.build_plan()
            assert plan.changes, module.slug
            assert all(change.title and change.detail for change in plan.changes), module.slug


def test_builtin_modules_expose_route_and_nav_metadata():
    registry = create_builtin_module_registry()

    for module in registry.list_modules():
        assert module.routes, module.slug
        assert module.nav_items, module.slug
        assert any(route.page for route in module.routes), module.slug
        assert all(isinstance(route, ModuleRoute) for route in module.routes)
        assert all(isinstance(item, ModuleNavItem) for item in module.nav_items)
        assert all(route.rule.startswith("/") and route.endpoint for route in module.routes)
        assert all(item.label and item.endpoint and item.icon for item in module.nav_items)

    storage = registry.module_for_slug("storage")
    assert storage.nav_items[0].active_endpoints == (
        "storage_routes.storage_page",
        "storage_routes.storage_change_drive_page",
        "storage_routes.storage_existing_folder_page",
    )
    assert registry.module_for_slug("ddns").nav_items[0].admin_only is True


def test_builtin_module_route_metadata_matches_registered_blueprints():
    app = Flask(__name__)
    for blueprint in module_blueprints():
        app.register_blueprint(blueprint)

    actual_routes = {
        (rule.endpoint, rule.rule): tuple(
            sorted(method for method in rule.methods if method not in {"HEAD", "OPTIONS"})
        )
        for rule in app.url_map.iter_rules()
        if rule.endpoint != "static"
    }
    declared_routes = {
        (route.endpoint, route.rule): tuple(route.methods)
        for module in create_builtin_module_registry().list_modules()
        for route in module.routes
    }

    assert declared_routes == actual_routes


def test_worker_jobs_are_declared_by_feature_modules():
    registry = create_builtin_module_registry()

    jobs_by_module = {
        module.slug: [job.name for job in module.jobs] for module in registry.list_modules()
    }

    assert jobs_by_module["cloud-backup"] == ["cloud-backup"]
    assert jobs_by_module["ddns"] == ["ddns-update"]
    assert jobs_by_module["drive-health"] == ["drive-health"]
    assert jobs_by_module["storage"] == ["mount-check"]
    assert jobs_by_module["alerts"] == []
    assert jobs_by_module["file-sharing"] == []
    assert jobs_by_module["system-updates"] == []


def test_scheduled_worker_root_actions_are_declared_by_modules():
    registry = create_builtin_module_registry()

    drive_health_plan = registry.module_for_slug("drive-health").build_plan()
    storage_plan = registry.module_for_slug("storage").build_plan()

    assert any(
        action.name == "drive-health.scheduled-check"
        for action in drive_health_plan.privileged_actions
    )
    assert any(action.name == "storage.mount-check" for action in storage_plan.privileged_actions)


def test_builtin_privileged_actions_are_declared_by_module_contracts():
    helper_actions = set(create_builtin_privileged_action_registry().list_actions())
    module_actions = {
        action.name
        for module in create_builtin_module_registry().list_modules()
        for action in module.privileged_actions
    }

    assert helper_actions == module_actions


def test_module_serialization_exposes_full_structured_help():
    module = create_builtin_module_registry().module_for_slug("storage")

    payload = module_data(module)

    assert payload["help"]["purpose"] == module.help.purpose
    assert payload["help"]["warnings"] == list(module.help.warnings)
    assert payload["help"]["field_help"][0]["key"] == "existing_folder"
    assert payload["help"]["confirmations"]
    assert payload["help"]["empty_states"]
    assert payload["help"]["success_messages"]
    assert payload["help"]["error_explanations"]
    assert payload["help"]["recovery_actions"]
    assert payload["routes"][0]["rule"] == "/storage"
    assert payload["routes"][0]["page"] is True
    assert payload["nav_items"][0]["label"] == "Storage"
    assert payload["nav_items"][0]["active_endpoints"]
    assert payload["jobs"][0]["name"] == "mount-check"
    assert payload["jobs"][0]["worker_scheduled"] is True

    plan_payload = module_plan_data(module.build_plan())
    resources = {item["identifier"]: item for item in plan_payload["owned_resources"]}
    assert resources["/etc/fstab#SimpleSaferServer managed backup drive"][
        "record_on_apply"
    ] is False
