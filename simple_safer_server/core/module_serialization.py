from __future__ import annotations

from typing import Any

from simple_safer_server.core.jobs import JobDefinition
from simple_safer_server.core.module_checks import (
    ModuleCheck,
    RequiredToolCheck,
    check_required_tools,
)
from simple_safer_server.core.module_contract import (
    HelpEntry,
    ModuleHelp,
    ModuleNavItem,
    ModulePlan,
    ModuleRoute,
    OwnedResource,
    PlanChange,
    PrivilegedAction,
    RequiredTool,
    SssModule,
)
from simple_safer_server.core.module_lifecycle import module_is_applied
from simple_safer_server.core.ownership import OwnershipRecord


def required_tool_data(tool: RequiredTool, check: RequiredToolCheck | None = None) -> dict[str, object]:
    data = {
        "name": tool.name,
        "purpose": tool.purpose,
        "optional": tool.optional,
    }
    if check is not None:
        data.update(
            {
                "available": check.available,
                "path": check.path,
                "blocking": check.blocking,
            }
        )
    return data


def required_tool_check_data(check: RequiredToolCheck) -> dict[str, object]:
    return {
        **required_tool_data(check.tool, check),
        "status": "available" if check.available else "missing",
    }


def owned_resource_data(resource: OwnedResource | OwnershipRecord) -> dict[str, object]:
    data = {
        "kind": resource.kind,
        "identifier": resource.identifier,
        "reason": resource.reason,
    }
    if isinstance(resource, OwnedResource):
        data["record_on_apply"] = resource.record_on_apply
    return data


def privileged_action_data(action: PrivilegedAction) -> dict[str, str]:
    return {
        "name": action.name,
        "description": action.description,
    }


def module_route_data(route: ModuleRoute) -> dict[str, object]:
    return {
        "rule": route.rule,
        "endpoint": route.endpoint,
        "methods": list(route.methods),
        "page": route.page,
    }


def module_nav_item_data(item: ModuleNavItem) -> dict[str, object]:
    return {
        "label": item.label,
        "endpoint": item.endpoint,
        "icon": item.icon,
        "order": item.order,
        "admin_only": item.admin_only,
        "active_endpoints": list(item.active_endpoints),
    }


def job_definition_data(job: JobDefinition) -> dict[str, object]:
    return {
        "name": job.name,
        "module_slug": job.module_slug,
        "title": job.title,
        "description": job.description,
        "task_name": job.task_name,
        "interval_seconds": job.interval_seconds,
        "daily_time_config_section": job.daily_time_config_section,
        "daily_time_config_key": job.daily_time_config_key,
        "default_daily_time": job.default_daily_time,
        "daily_time_offset_minutes": job.daily_time_offset_minutes,
        "enabled_config_section": job.enabled_config_section,
        "enabled_config_key": job.enabled_config_key,
        "enabled_config_value": job.enabled_config_value,
        "worker_scheduled": job.is_worker_scheduled,
    }


def help_entry_data(entry: HelpEntry) -> dict[str, str]:
    return {
        "key": entry.key,
        "text": entry.text,
    }


def help_entries_data(entries: tuple[HelpEntry, ...]) -> list[dict[str, str]]:
    return [help_entry_data(entry) for entry in entries]


def module_help_data(help_text: ModuleHelp) -> dict[str, object]:
    return {
        "purpose": help_text.purpose,
        "setup_intro": help_text.setup_intro,
        "warnings": list(help_text.warnings),
        "docs_path": help_text.docs_path,
        "field_help": help_entries_data(help_text.field_help),
        "tooltips": help_entries_data(help_text.tooltips),
        "empty_states": help_entries_data(help_text.empty_states),
        "confirmations": help_entries_data(help_text.confirmations),
        "success_messages": help_entries_data(help_text.success_messages),
        "error_explanations": help_entries_data(help_text.error_explanations),
        "recovery_actions": help_entries_data(help_text.recovery_actions),
    }


def plan_change_data(change: PlanChange) -> dict[str, object]:
    return {
        "title": change.title,
        "detail": change.detail,
        "requires_privilege": change.requires_privilege,
    }


def module_data(module: SssModule, runtime: Any | None = None) -> dict[str, object]:
    data = {
        "slug": module.slug,
        "title": module.title,
        "description": module.description,
        "state": module.state.value,
        "docs_path": module.help.docs_path,
        "purpose": module.help.purpose,
        "help": module_help_data(module.help),
        "routes": [module_route_data(route) for route in module.routes],
        "nav_items": [module_nav_item_data(item) for item in module.nav_items],
        "jobs": [job_definition_data(job) for job in module.jobs],
    }
    if runtime is not None:
        data["applied"] = module_is_applied(module, runtime)
    return data


def module_check_data(check: ModuleCheck) -> dict[str, object]:
    return {
        "module_slug": check.module_slug,
        "summary": check.summary,
        "blocking": check.blocking,
        "required_tools": [
            required_tool_check_data(tool_check) for tool_check in check.required_tools
        ],
    }


def module_plan_data(plan: ModulePlan) -> dict[str, object]:
    tool_checks = {
        tool_check.tool.name: tool_check
        for tool_check in check_required_tools(plan.required_tools)
    }
    return {
        "module_slug": plan.module_slug,
        "summary": plan.summary,
        "changes": [plan_change_data(change) for change in plan.changes],
        "warnings": list(plan.warnings),
        "owned_resources": [owned_resource_data(resource) for resource in plan.owned_resources],
        "required_tools": [
            required_tool_data(tool, tool_checks.get(tool.name)) for tool in plan.required_tools
        ],
        "privileged_actions": [
            privileged_action_data(action) for action in plan.privileged_actions
        ],
    }


def ownership_record_data(record: OwnershipRecord) -> dict[str, str]:
    return {
        "module_slug": record.module_slug,
        **owned_resource_data(record),
    }
