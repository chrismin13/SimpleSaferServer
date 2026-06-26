from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from simple_safer_server.core.module_checks import check_module_requirements
from simple_safer_server.core.module_contract import ModuleState, OwnedResource, SssModule
from simple_safer_server.core.ownership import OwnershipManifest, OwnershipRecord


class ModuleLifecycleError(RuntimeError):
    """Raised when a module lifecycle action is not valid for the module."""


@dataclass(frozen=True)
class ModuleApplyResult:
    module_slug: str
    recorded: tuple[OwnershipRecord, ...]


@dataclass(frozen=True)
class ModuleUninstallResult:
    module_slug: str
    removed: tuple[OwnershipRecord, ...]
    removed_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class _AppOwnedCleanupPlan:
    file_paths: tuple[Path, ...] = ()
    config_sections: tuple[str, ...] = ()
    secret_keys: tuple[str, ...] = ()


def ownership_manifest_path(runtime: Any) -> Path:
    return Path(runtime.data_dir) / "ownership.json"


def ownership_manifest_for_runtime(runtime: Any) -> OwnershipManifest:
    return OwnershipManifest(ownership_manifest_path(runtime))


def module_is_applied(module: SssModule, runtime: Any) -> bool:
    """Return whether a writable module has recorded setup ownership."""
    if module.state == ModuleState.READ_ONLY:
        return False
    if not module.owned_resources:
        return True
    manifest = ownership_manifest_for_runtime(runtime)
    return any(record.module_slug == module.slug for record in manifest.list_records())


def module_apply_resources(module: SssModule) -> tuple[OwnedResource, ...]:
    """Return the ownership records that generic module apply may create."""
    return tuple(resource for resource in module.owned_resources if resource.record_on_apply)


def require_module_applied(module: SssModule, runtime: Any) -> None:
    """Stop host-writing routes until the module setup flow has recorded ownership."""
    if module.state == ModuleState.READ_ONLY:
        raise ModuleLifecycleError(f"{module.title} is read-only and cannot write config.")
    if not module_is_applied(module, runtime):
        raise ModuleLifecycleError(
            f"{module.title} must be applied before it can write config."
        )


def ensure_module_can_apply(module: SssModule) -> None:
    """Run apply preflight checks without recording ownership."""
    if module.state == ModuleState.READ_ONLY:
        raise ModuleLifecycleError(f"{module.title} is read-only and has no setup action.")
    check = check_module_requirements(module)
    missing_required_tools = tuple(
        tool_check.tool.name for tool_check in check.required_tools if tool_check.blocking
    )
    if missing_required_tools:
        tools = ", ".join(missing_required_tools)
        raise ModuleLifecycleError(
            f"{module.title} cannot be applied because required tools are missing: {tools}."
        )


def apply_module(module: SssModule, runtime: Any) -> ModuleApplyResult:
    """Record the resources a module contract says SSS owns."""
    ensure_module_can_apply(module)
    manifest = ownership_manifest_for_runtime(runtime)
    recorded = manifest.record_module_resources(module.slug, module_apply_resources(module))
    return ModuleApplyResult(module_slug=module.slug, recorded=recorded)


def _app_owned_path(runtime: Any, record: OwnershipRecord) -> Path | None:
    if record.kind not in {"config-file", "state-file"}:
        return None
    if record.identifier.startswith("<config>/"):
        root = getattr(runtime, "config_dir", None)
        prefix = "<config>/"
    elif record.identifier.startswith("<data>/"):
        root = getattr(runtime, "data_dir", None)
        prefix = "<data>/"
    else:
        return _safe_absolute_app_owned_path(runtime, record)
    if root is None:
        return None
    relative = Path(record.identifier.removeprefix(prefix))
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ModuleLifecycleError(f"Unsafe app-owned path in ownership record: {record.identifier}")
    return Path(root) / relative


def _safe_absolute_app_owned_path(runtime: Any, record: OwnershipRecord) -> Path | None:
    """Return an absolute app-owned file path only when it stays inside SSS dirs."""
    path = Path(record.identifier)
    if not path.is_absolute():
        return None
    allowed_roots = [
        Path(root).resolve()
        for root in (getattr(runtime, "config_dir", None), getattr(runtime, "data_dir", None))
        if root is not None
    ]
    if not allowed_roots:
        return None
    resolved = path.resolve()
    if any(resolved == root or root in resolved.parents for root in allowed_roots):
        return path
    return None


def _parse_single_bracket_identifier(
    identifier: str, *, prefix: str, label: str
) -> tuple[str, ...] | None:
    if not identifier.startswith(prefix) or not identifier.endswith("]"):
        return None
    raw_values = identifier.removeprefix(prefix)[:-1]
    values = tuple(value.strip() for value in raw_values.split(",") if value.strip())
    if not values:
        raise ModuleLifecycleError(f"Unsafe empty {label} ownership record: {identifier}")
    if any(any(char in value for char in "[]/\\") for value in values):
        raise ModuleLifecycleError(f"Unsafe {label} ownership record: {identifier}")
    return values


def _app_owned_cleanup_plan(
    runtime: Any, records: tuple[OwnershipRecord, ...]
) -> _AppOwnedCleanupPlan:
    paths: list[Path] = []
    config_sections: list[str] = []
    secret_keys: list[str] = []
    unsupported: list[OwnershipRecord] = []
    for record in records:
        if record.kind in {"config-file", "state-file"}:
            path = _app_owned_path(runtime, record)
            if path is None:
                unsupported.append(record)
            else:
                paths.append(path)
            continue
        if record.kind == "config-section":
            sections = _parse_single_bracket_identifier(
                record.identifier,
                prefix="<config>/config.conf[",
                label="config-section",
            )
            if sections is None:
                unsupported.append(record)
            else:
                config_sections.extend(sections)
            continue
        if record.kind == "config-secret":
            keys = _parse_single_bracket_identifier(
                record.identifier,
                prefix="<config>/.secrets[",
                label="config-secret",
            )
            if keys is None:
                unsupported.append(record)
            else:
                secret_keys.extend(keys)
            continue
        if record.kind == "module-state":
            continue
        unsupported.append(record)
    if unsupported:
        details = ", ".join(
            f"{record.kind} {record.identifier}" for record in sorted(unsupported, key=str)
        )
        raise ModuleLifecycleError(
            "Generic module uninstall cannot remove these owned resources safely: "
            f"{details}. Add module-specific cleanup first."
        )
    return _AppOwnedCleanupPlan(
        file_paths=tuple(paths),
        config_sections=tuple(dict.fromkeys(config_sections)),
        secret_keys=tuple(dict.fromkeys(secret_keys)),
    )


def _remove_app_owned_resources(runtime: Any, plan: _AppOwnedCleanupPlan) -> tuple[str, ...]:
    removed: list[str] = []
    for path in plan.file_paths:
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ModuleLifecycleError(f"Could not remove app-owned file {path}: {exc}") from exc
        removed.append(str(path))
    if plan.config_sections or plan.secret_keys:
        from simple_safer_server.services.config_manager import ConfigManager

        config_manager = ConfigManager(runtime=runtime)
        for section in plan.config_sections:
            config_manager.remove_section(section)
        for key in plan.secret_keys:
            config_manager.delete_secret(key)
    return tuple(removed)


def uninstall_module(module: SssModule, runtime: Any) -> ModuleUninstallResult:
    """Remove safe app-owned files and this module's ownership records.

    Host-file deletion still needs module-specific cleanup so SSS never removes
    an admin-owned path just because a text identifier looks like a filename.
    """
    if module.state == ModuleState.READ_ONLY:
        raise ModuleLifecycleError(f"{module.title} is read-only and has no uninstall action.")
    manifest = ownership_manifest_for_runtime(runtime)
    current_records = tuple(
        record for record in manifest.list_records() if record.module_slug == module.slug
    )
    cleanup_plan = _app_owned_cleanup_plan(runtime, current_records)
    removed_paths = _remove_app_owned_resources(runtime, cleanup_plan)
    removed = manifest.remove_module_records(module.slug)
    return ModuleUninstallResult(
        module_slug=module.slug,
        removed=removed,
        removed_paths=removed_paths,
    )
