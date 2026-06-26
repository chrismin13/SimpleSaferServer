from __future__ import annotations

from simple_safer_server.core.job_action_client import run_privileged_job_action
from simple_safer_server.modules.ddns import updater


def run_update_job_direct() -> int:
    """Run the DDNS provider update implementation inside the helper process."""
    return int(updater.main() or 0)


def run_update_job() -> int:
    """Request a DDNS update through the allowlisted privileged helper."""
    return run_privileged_job_action("ddns.update")
