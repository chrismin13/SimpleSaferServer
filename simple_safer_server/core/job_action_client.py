from __future__ import annotations

import sys

from simple_safer_server.core.privileged_client import (
    PrivilegedActionClient,
    PrivilegedActionClientError,
)


def run_privileged_job_action(action: str) -> int:
    """Run one worker job action through sss-helper and return a process-style code."""
    try:
        PrivilegedActionClient().run(action, {})
    except PrivilegedActionClientError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code or 1
    return 0
