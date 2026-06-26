from __future__ import annotations

from typing import Any

from simple_safer_server.adapters.command_runner import CommandRunner
from simple_safer_server.adapters.storage_commands import StorageCommandAdapter
from simple_safer_server.core.job_action_client import run_privileged_job_action
from simple_safer_server.modules.alerts.notifications import AlertNotifier
from simple_safer_server.modules.storage.service import StorageService
from simple_safer_server.services.config_manager import ConfigManager
from simple_safer_server.services.runtime import get_fake_state, get_runtime
from simple_safer_server.services.system_utils import SystemUtils
from simple_safer_server.web.problems import OperationProblem, ValidationProblem


def run_mount_check_job_direct(
    *,
    runtime: Any | None = None,
    config_manager: Any | None = None,
    system_utils: Any | None = None,
    storage_service: StorageService | None = None,
) -> int:
    """Run the managed-drive mount check inside the helper process."""
    runtime = runtime or get_runtime()
    command_runner = CommandRunner()
    config_manager = config_manager or ConfigManager(runtime=runtime)
    system_utils = system_utils or SystemUtils(runtime=runtime, command_runner=command_runner)
    storage_service = storage_service or StorageService(
        runtime=runtime,
        fake_state=get_fake_state(runtime) if runtime.is_fake else None,
        config_manager=config_manager,
        command_adapter=StorageCommandAdapter(command_runner),
        system_utils=system_utils,
        command_runner=command_runner,
    )
    try:
        print(storage_service.mount_dashboard_drive())
    except (OperationProblem, ValidationProblem, OSError, RuntimeError) as exc:
        message = str(exc)
        print(message)
        AlertNotifier(config_manager, runtime).notify(
            "Backup Source Check Failed",
            message,
            alert_type="error",
            source="check_mount",
        )
        return 1
    return 0


def run_mount_check_job() -> int:
    """Request the managed-drive mount check through the helper."""
    return run_privileged_job_action("storage.mount-check")
