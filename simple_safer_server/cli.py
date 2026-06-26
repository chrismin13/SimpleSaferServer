from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import TextIO

from simple_safer_server.core.builtin_modules import create_builtin_module_registry
from simple_safer_server.core.job_runner import create_builtin_job_runner
from simple_safer_server.core.job_scheduler import WorkerScheduler
from simple_safer_server.core.job_state import JobStateStore
from simple_safer_server.core.jobs import JobDefinition, create_builtin_job_registry
from simple_safer_server.core.module_checks import check_module_requirements, check_required_tools
from simple_safer_server.core.module_contract import ModulePlan, SssModule
from simple_safer_server.core.module_lifecycle import (
    ModuleLifecycleError,
    apply_module,
    module_is_applied,
    uninstall_module,
)
from simple_safer_server.core.ownership import OwnershipRecord
from simple_safer_server.core.privileged_actions import create_builtin_privileged_action_registry
from simple_safer_server.modules.alerts.notifications import AlertNotifier
from simple_safer_server.services.config_manager import ConfigManager
from simple_safer_server.services.runtime import get_runtime


def _print_module_table(modules: tuple[SssModule, ...], stdout: TextIO) -> None:
    runtime = get_runtime()
    print("Slug             State          Applied  Title", file=stdout)
    print("---------------  -------------  -------  ----------------", file=stdout)
    for module in modules:
        applied = "yes" if module_is_applied(module, runtime) else "no"
        print(
            f"{module.slug:<15}  {module.state.value:<13}  {applied:<7}  {module.title}",
            file=stdout,
        )


def _print_plan(plan: ModulePlan, stdout: TextIO) -> None:
    print(f"Module: {plan.module_slug}", file=stdout)
    print(f"Summary: {plan.summary}", file=stdout)

    if plan.required_tools:
        print("\nRequired tools:", file=stdout)
        tool_checks = {
            tool_check.tool.name: tool_check
            for tool_check in check_required_tools(plan.required_tools)
        }
        for tool in plan.required_tools:
            suffix = " (optional)" if tool.optional else ""
            check = tool_checks.get(tool.name)
            status = "available" if check and check.available else "missing"
            path = f" at {check.path}" if check and check.path else ""
            print(f"- {tool.name}{suffix} [{status}{path}]: {tool.purpose}", file=stdout)

    if plan.changes:
        print("\nPlanned changes:", file=stdout)
        for change in plan.changes:
            suffix = " [privileged]" if change.requires_privilege else ""
            print(f"- {change.title}{suffix}: {change.detail}", file=stdout)

    if plan.owned_resources:
        print("\nOwned resources:", file=stdout)
        for resource in plan.owned_resources:
            timing = "" if resource.record_on_apply else " [recorded after specific write]"
            print(
                f"- {resource.kind} {resource.identifier}{timing}: {resource.reason}",
                file=stdout,
            )

    if plan.privileged_actions:
        print("\nPrivileged actions:", file=stdout)
        for action in plan.privileged_actions:
            print(f"- {action.name}: {action.description}", file=stdout)

    if plan.warnings:
        print("\nWarnings:", file=stdout)
        for warning in plan.warnings:
            print(f"- {warning}", file=stdout)


def _print_ownership_records(title: str, records: tuple[OwnershipRecord, ...], stdout: TextIO) -> None:
    print(title, file=stdout)
    if not records:
        print("- none", file=stdout)
        return
    for record in records:
        print(f"- {record.kind} {record.identifier}: {record.reason}", file=stdout)


def _print_job_table(jobs: tuple[JobDefinition, ...], stdout: TextIO) -> None:
    print("Name           Module          Schedule", file=stdout)
    print("-------------  --------------  ------------------", file=stdout)
    for job in jobs:
        if job.interval_seconds:
            schedule = f"worker every {job.interval_seconds}s"
        elif job.is_daily_scheduled:
            schedule = f"worker daily {job.default_daily_time}"
            if job.daily_time_offset_minutes:
                schedule = f"{schedule} {job.daily_time_offset_minutes:+d}m"
        else:
            schedule = "manual"
        print(f"{job.name:<13}  {job.module_slug:<14}  {schedule}", file=stdout)


def _print_doctor(modules: tuple[SssModule, ...], stdout: TextIO) -> None:
    runtime = get_runtime()
    print("SimpleSaferServer doctor", file=stdout)
    print(f"- mode: {runtime.mode}", file=stdout)
    print(f"- app data: {runtime.data_dir}", file=stdout)
    print(f"- config: {runtime.config_dir}", file=stdout)
    print(f"- logs: {runtime.logs_dir}", file=stdout)
    print(f"- privileged actions: {len(create_builtin_privileged_action_registry().list_actions())}", file=stdout)
    print("", file=stdout)
    print("Module tools", file=stdout)
    for module in modules:
        check = check_module_requirements(module)
        if not check.required_tools:
            continue
        for tool_check in check.required_tools:
            status = "available" if tool_check.available else "missing"
            suffix = "optional" if tool_check.tool.optional else "needed when enabled"
            print(f"- {module.slug}: {tool_check.tool.name} {status} ({suffix})", file=stdout)


def _print_module_check(module: SssModule, stdout: TextIO) -> None:
    check = check_module_requirements(module)
    print(f"Module: {check.module_slug}", file=stdout)
    print(f"Summary: {check.summary}", file=stdout)
    if not check.required_tools:
        return
    print("\nTool checks:", file=stdout)
    for tool_check in check.required_tools:
        status = "available" if tool_check.available else "missing"
        suffix = " (optional)" if tool_check.tool.optional else ""
        path = f" at {tool_check.path}" if tool_check.path else ""
        print(
            f"- {tool_check.tool.name}{suffix}: {status}{path} - {tool_check.tool.purpose}",
            file=stdout,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sss",
        description="Operate SimpleSaferServer from the terminal.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("status", help="Show basic SimpleSaferServer CLI status.")
    subcommands.add_parser("doctor", help="Run read-only SimpleSaferServer checks.")

    module_parser = subcommands.add_parser("module", help="Inspect managed modules.")
    module_subcommands = module_parser.add_subparsers(dest="module_command", required=True)
    module_subcommands.add_parser("list", help="List known modules.")
    module_check_parser = module_subcommands.add_parser(
        "check",
        help="Run read-only setup checks for a module.",
    )
    module_check_parser.add_argument("slug", help="Module slug, such as cloud-backup or storage.")
    module_plan_parser = module_subcommands.add_parser("plan", help="Show a module setup plan.")
    module_plan_parser.add_argument("slug", help="Module slug, such as cloud-backup or storage.")
    module_apply_parser = module_subcommands.add_parser(
        "apply",
        help="Record generic apply-time ownership for a module.",
    )
    module_apply_parser.add_argument("slug", help="Module slug, such as cloud-backup or storage.")
    module_uninstall_parser = module_subcommands.add_parser(
        "uninstall",
        help="Remove a module's ownership records from the manifest.",
    )
    module_uninstall_parser.add_argument(
        "slug",
        help="Module slug, such as cloud-backup or storage.",
    )

    job_parser = subcommands.add_parser("job", help="Inspect worker jobs.")
    job_subcommands = job_parser.add_subparsers(dest="job_command", required=True)
    job_subcommands.add_parser("list", help="List worker jobs.")
    job_run_parser = job_subcommands.add_parser("run", help="Run a worker job.")
    job_run_parser.add_argument("name", help="Job name.")

    alert_parser = subcommands.add_parser("alert", help="Create alerts and send notifications.")
    alert_subcommands = alert_parser.add_subparsers(dest="alert_command", required=True)
    alert_send_parser = alert_subcommands.add_parser("send", help="Log and send an alert.")
    alert_send_parser.add_argument("title")
    alert_send_parser.add_argument("message")
    alert_send_parser.add_argument("--type", default="error", dest="alert_type")
    alert_send_parser.add_argument("--source", default="sss")

    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)
    registry = create_builtin_module_registry()
    job_registry = create_builtin_job_registry()

    if args.command == "status":
        print("SimpleSaferServer CLI is available.", file=stdout)
        print(f"Registered modules: {len(registry.list_modules())}", file=stdout)
        print(f"Registered worker jobs: {len(job_registry.list_jobs())}", file=stdout)
        print("Worker service: simple-safer-server-worker.service", file=stdout)
        return 0

    if args.command == "doctor":
        _print_doctor(registry.list_modules(), stdout)
        return 0

    if args.command == "module":
        if args.module_command == "list":
            _print_module_table(registry.list_modules(), stdout)
            return 0
        try:
            module = registry.module_for_slug(args.slug)
        except KeyError:
            print(f"Unknown module: {args.slug}", file=stderr)
            return 2
        if args.module_command == "plan":
            _print_plan(module.build_plan(), stdout)
            return 0
        if args.module_command == "check":
            _print_module_check(module, stdout)
            return 0
        if args.module_command == "apply":
            try:
                result = apply_module(module, get_runtime())
            except ModuleLifecycleError as exc:
                print(str(exc), file=stderr)
                return 2
            _print_ownership_records(
                f"Recorded ownership for module: {result.module_slug}",
                result.recorded,
                stdout,
            )
            return 0
        if args.module_command == "uninstall":
            try:
                result = uninstall_module(module, get_runtime())
            except ModuleLifecycleError as exc:
                print(str(exc), file=stderr)
                return 2
            _print_ownership_records(
                f"Removed ownership records for module: {result.module_slug}",
                result.removed,
                stdout,
            )
            print(
                "Module uninstall removed only records that were safe for generic cleanup. "
                "Module-specific cleanup must remove host files safely before records are forgotten.",
                file=stdout,
            )
            if result.removed_paths:
                print("\nRemoved app-owned files:", file=stdout)
                for path in result.removed_paths:
                    print(f"- {path}", file=stdout)
            return 0

    if args.command == "job":
        if args.job_command == "list":
            _print_job_table(job_registry.list_jobs(), stdout)
            return 0
        if args.job_command == "run":
            try:
                job = job_registry.job_for_name(args.name)
                runtime = get_runtime()
                scheduler = WorkerScheduler(
                    job_registry,
                    create_builtin_job_runner(job_registry),
                    JobStateStore(runtime),
                    config_manager=ConfigManager(runtime=runtime),
                    module_registry=registry,
                )
                result = scheduler.run_job(job)
            except KeyError:
                print(f"Unknown job: {args.name}", file=stderr)
                return 2
            except NotImplementedError as exc:
                print(str(exc), file=stderr)
                return 2
            except ModuleLifecycleError as exc:
                print(str(exc), file=stderr)
                return 2
            print(f"{args.name}: {result.message}", file=stdout)
            return result.exit_code

    if args.command == "alert" and args.alert_command == "send":
        runtime = get_runtime()
        AlertNotifier(ConfigManager(runtime=runtime), runtime).notify(
            args.title,
            args.message,
            alert_type=args.alert_type,
            source=args.source,
        )
        print(f"Alert sent: {args.title}", file=stdout)
        return 0

    parser.error("Unsupported command.")
    return 2


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
