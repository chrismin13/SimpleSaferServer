#!/usr/bin/env python3

import sys
from pathlib import Path


def _add_app_to_path():
    script_path = Path(__file__).resolve()
    candidates = [
        script_path.parents[1],
        Path('/opt/SimpleSaferServer'),
    ]
    for candidate in candidates:
        if (candidate / 'drive_health.py').exists():
            sys.path.insert(0, str(candidate))
            return


_add_app_to_path()

from config_manager import ConfigManager  # noqa: E402
from drive_health import run_scheduled_drive_health_check  # noqa: E402
from runtime import get_runtime  # noqa: E402
from system_utils import SystemUtils  # noqa: E402


def main():
    runtime = get_runtime()
    config_manager = ConfigManager(runtime=runtime)
    system_utils = SystemUtils(runtime=runtime)

    result = run_scheduled_drive_health_check(
        config_manager,
        system_utils,
        runtime=runtime,
    )

    probability = result.get('probability')
    device = result.get('device')
    if probability is not None and device:
        print(f"Drive health probability for {device}: {probability:.4f}")

    hdsentinel_snapshot = result.get('hdsentinel', {}).get('snapshot')
    if hdsentinel_snapshot and hdsentinel_snapshot.get('available'):
        print(
            "HDSentinel: "
            f"health {hdsentinel_snapshot.get('health_pct')}%, "
            f"performance {hdsentinel_snapshot.get('performance_pct')}%, "
            f"temperature {hdsentinel_snapshot.get('temperature_c')}C"
        )
    elif hdsentinel_snapshot and hdsentinel_snapshot.get('error'):
        print(f"HDSentinel unavailable: {hdsentinel_snapshot['error']}")


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
