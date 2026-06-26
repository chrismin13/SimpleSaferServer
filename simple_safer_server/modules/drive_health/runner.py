from __future__ import annotations

from typing import Any

from simple_safer_server.core.job_action_client import run_privileged_job_action
from simple_safer_server.modules.drive_health.service import (
    hdsentinel_snapshot_has_health,
    run_scheduled_drive_health_check,
)
from simple_safer_server.services.config_manager import ConfigManager
from simple_safer_server.services.runtime import get_runtime
from simple_safer_server.services.system_utils import SystemUtils


def _print_drive_health_summary(result: dict[str, Any]) -> None:
    if result.get("smart") is not None and result.get("device"):
        print(f"SMART details collected for {result['device']}.")

    hdsentinel_snapshot = result.get("hdsentinel", {}).get("snapshot")
    if hdsentinel_snapshot_has_health(hdsentinel_snapshot):
        print(
            "HDSentinel: "
            f"health {hdsentinel_snapshot.get('health_pct')}%, "
            f"performance {hdsentinel_snapshot.get('performance_pct')}%, "
            f"temperature {hdsentinel_snapshot.get('temperature_c')}C"
        )
    elif hdsentinel_snapshot and hdsentinel_snapshot.get("error"):
        print(f"HDSentinel unavailable: {hdsentinel_snapshot['error']}")


def run_drive_health_job_direct(
    *,
    runtime: Any | None = None,
    config_manager: Any | None = None,
    system_utils: Any | None = None,
) -> int:
    """Run the drive health check inside the helper process."""
    try:
        runtime = runtime or get_runtime()
        config_manager = config_manager or ConfigManager(runtime=runtime)
        system_utils = system_utils or SystemUtils(runtime=runtime)
        result = run_scheduled_drive_health_check(
            config_manager,
            system_utils,
            runtime=runtime,
        )
        _print_drive_health_summary(result)
    except Exception as exc:
        print(str(exc))
        return 1
    return 0


def run_drive_health_job() -> int:
    """Request the scheduled drive health check through the helper."""
    return run_privileged_job_action("drive-health.scheduled-check")
