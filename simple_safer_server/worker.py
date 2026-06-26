from __future__ import annotations

import argparse
import signal
import sys
import time

from simple_safer_server.core.builtin_modules import create_builtin_module_registry
from simple_safer_server.core.job_runner import create_builtin_job_runner
from simple_safer_server.core.job_scheduler import WorkerScheduler
from simple_safer_server.core.job_state import JobStateStore
from simple_safer_server.core.jobs import create_builtin_job_registry
from simple_safer_server.core.module_lifecycle import ModuleLifecycleError
from simple_safer_server.services.config_manager import ConfigManager


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the SimpleSaferServer worker service.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run currently due worker jobs once and exit. Useful for diagnostics.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=int,
        default=60,
        help="Seconds to sleep between worker checks.",
    )
    parser.add_argument(
        "--run-job",
        help="Run one registered job by name and exit.",
    )
    return parser


def run(
    argv: list[str] | None = None,
    *,
    state_store: JobStateStore | None = None,
    config_manager: ConfigManager | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    module_registry = create_builtin_module_registry()
    registry = create_builtin_job_registry()
    stopping = False

    def stop_worker(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop_worker)
    signal.signal(signal.SIGINT, stop_worker)

    print(f"SimpleSaferServer worker loaded {len(registry.list_jobs())} planned jobs.")
    runner = create_builtin_job_runner(registry)
    scheduler = WorkerScheduler(
        registry,
        runner,
        state_store or JobStateStore(),
        config_manager=config_manager or ConfigManager(),
        module_registry=module_registry,
    )

    if args.run_job:
        try:
            job = registry.job_for_name(args.run_job)
            result = scheduler.run_job(job)
        except KeyError:
            print(f"Unknown job: {args.run_job}", file=sys.stderr)
            return 2
        except NotImplementedError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except ModuleLifecycleError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"{args.run_job}: {result.message}")
        return result.exit_code

    if args.once:
        ran = scheduler.run_due_jobs()
        if ran:
            print("Ran due jobs: {}".format(", ".join(ran)))
        else:
            print("No worker jobs were due.")
        return 0

    while not stopping:
        ran = scheduler.run_due_jobs()
        if ran:
            print("Ran due jobs: {}".format(", ".join(ran)), flush=True)
        wait = scheduler.seconds_until_next_due()
        sleep_seconds = max(1, args.sleep_seconds)
        if wait is not None:
            sleep_seconds = max(1, min(sleep_seconds, wait))
        time.sleep(sleep_seconds)
    print("SimpleSaferServer worker stopped.")
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
