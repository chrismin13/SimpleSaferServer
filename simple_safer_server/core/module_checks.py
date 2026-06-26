from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass

from simple_safer_server.core.module_contract import RequiredTool, SssModule

ToolFinder = Callable[[str], str | None]


@dataclass(frozen=True)
class RequiredToolCheck:
    tool: RequiredTool
    available: bool
    path: str

    @property
    def blocking(self) -> bool:
        return not self.available and not self.tool.optional


@dataclass(frozen=True)
class ModuleCheck:
    module_slug: str
    required_tools: tuple[RequiredToolCheck, ...]

    @property
    def blocking(self) -> bool:
        return any(tool_check.blocking for tool_check in self.required_tools)

    @property
    def summary(self) -> str:
        if not self.required_tools:
            return "This module does not declare external tools."
        if self.blocking:
            return "Required tools are missing."
        return "Required tools are available."


def check_module_requirements(
    module: SssModule,
    *,
    tool_finder: ToolFinder | None = None,
) -> ModuleCheck:
    """Return read-only setup checks for a module before any host writes."""
    return ModuleCheck(
        module_slug=module.slug,
        required_tools=check_required_tools(module.required_tools, tool_finder=tool_finder),
    )


def check_required_tools(
    required_tools: tuple[RequiredTool, ...],
    *,
    tool_finder: ToolFinder | None = None,
) -> tuple[RequiredToolCheck, ...]:
    """Check declared tool availability without needing a full module object."""
    finder = tool_finder or shutil.which
    return tuple(
        RequiredToolCheck(
            tool=tool,
            available=bool(path := finder(tool.name)),
            path=path or "",
        )
        for tool in required_tools
    )
