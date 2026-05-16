#!/usr/bin/env python3
"""Restore expired SimpleSaferServer-managed task schedule disables."""

import logging
import sys
from pathlib import Path


def _add_app_to_path():
    script_path = Path(__file__).resolve()
    candidates = [
        script_path.parents[1],
        Path("/opt/SimpleSaferServer"),
    ]
    for candidate in candidates:
        if (candidate / "simple_safer_server").exists():
            sys.path.insert(0, str(candidate))
            return


_add_app_to_path()

from simple_safer_server.adapters.systemd import SystemdAdapter  # noqa: E402
from simple_safer_server.services.alert_notifications import AlertNotifier  # noqa: E402
from simple_safer_server.services.config_manager import ConfigManager  # noqa: E402
from simple_safer_server.services.disabled_timers import DisabledTimerService  # noqa: E402
from simple_safer_server.services.runtime import get_runtime  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
LOGGER = logging.getLogger(__name__)


def main():
    runtime = get_runtime()
    config_manager = ConfigManager(runtime=runtime)
    systemd_adapter = SystemdAdapter()
    notifier = AlertNotifier(config_manager, runtime)
    service = DisabledTimerService(
        runtime,
        systemd_adapter,
        alert_notifier=notifier,
    )
    LOGGER.info("Starting disabled timer restore check")
    try:
        result = service.restore_expired()
    except Exception:
        # The restore helper is timer-driven, so journal-visible failures are important when
        # diagnosing why temporary Disable Schedule records did not recover automatically.
        LOGGER.exception("Disabled timer restore check failed")
        return 1

    LOGGER.info(
        "Disabled timer restore check completed: restored=%s failed=%s",
        len(result.get("restored", [])),
        len(result.get("failed", [])),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
