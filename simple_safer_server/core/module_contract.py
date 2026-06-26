from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from simple_safer_server.core.jobs import JobDefinition


class ModuleState(StrEnum):
    """Broad lifecycle state for modules during the redesign."""

    ACTIVE = "active"
    PLANNED = "planned"
    OPTIONAL = "optional"
    READ_ONLY = "read-only"


@dataclass(frozen=True)
class RequiredTool:
    name: str
    purpose: str
    optional: bool = False


@dataclass(frozen=True)
class OwnedResource:
    kind: str
    identifier: str
    reason: str
    record_on_apply: bool = True


@dataclass(frozen=True)
class PrivilegedAction:
    name: str
    description: str


@dataclass(frozen=True)
class ModuleRoute:
    rule: str
    endpoint: str
    methods: tuple[str, ...] = ("GET",)
    page: bool = False


@dataclass(frozen=True)
class ModuleNavItem:
    label: str
    endpoint: str
    icon: str
    order: int
    admin_only: bool = False
    active_endpoints: tuple[str, ...] = ()


@dataclass(frozen=True)
class HelpEntry:
    key: str
    text: str


@dataclass(frozen=True)
class ModuleHelp:
    purpose: str
    setup_intro: str = ""
    warnings: tuple[str, ...] = ()
    docs_path: str = ""
    field_help: tuple[HelpEntry, ...] = ()
    tooltips: tuple[HelpEntry, ...] = ()
    empty_states: tuple[HelpEntry, ...] = ()
    confirmations: tuple[HelpEntry, ...] = ()
    success_messages: tuple[HelpEntry, ...] = ()
    error_explanations: tuple[HelpEntry, ...] = ()
    recovery_actions: tuple[HelpEntry, ...] = ()


@dataclass(frozen=True)
class PlanChange:
    title: str
    detail: str
    requires_privilege: bool = False


@dataclass(frozen=True)
class ModulePlan:
    module_slug: str
    summary: str
    changes: tuple[PlanChange, ...] = ()
    warnings: tuple[str, ...] = ()
    owned_resources: tuple[OwnedResource, ...] = ()
    required_tools: tuple[RequiredTool, ...] = ()
    privileged_actions: tuple[PrivilegedAction, ...] = ()


@dataclass(frozen=True)
class SssModule:
    slug: str
    title: str
    description: str
    state: ModuleState
    help: ModuleHelp
    required_tools: tuple[RequiredTool, ...] = ()
    routes: tuple[ModuleRoute, ...] = ()
    nav_items: tuple[ModuleNavItem, ...] = ()
    jobs: tuple[JobDefinition, ...] = ()
    owned_resources: tuple[OwnedResource, ...] = ()
    privileged_actions: tuple[PrivilegedAction, ...] = ()
    plan_changes: tuple[PlanChange, ...] = ()
    plan_warnings: tuple[str, ...] = field(default_factory=tuple)

    def build_plan(self) -> ModulePlan:
        """Return the current setup plan shape without applying host changes."""
        return ModulePlan(
            module_slug=self.slug,
            summary=self.help.setup_intro or self.description,
            changes=self.plan_changes,
            warnings=self.plan_warnings or self.help.warnings,
            owned_resources=self.owned_resources,
            required_tools=self.required_tools,
            privileged_actions=self.privileged_actions,
        )


class ModuleRegistry:
    def __init__(self, modules: list[SssModule] | tuple[SssModule, ...]):
        slugs = [module.slug for module in modules]
        if len(slugs) != len(set(slugs)):
            raise ValueError("Module slugs must be unique.")
        self._modules = tuple(sorted(modules, key=lambda module: module.slug))

    def list_modules(self) -> tuple[SssModule, ...]:
        return self._modules

    def module_for_slug(self, slug: str) -> SssModule:
        for module in self._modules:
            if module.slug == slug:
                return module
        raise KeyError(slug)
