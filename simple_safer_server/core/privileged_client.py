from __future__ import annotations

import json
import os
import shlex
import shutil
import sys
from dataclasses import dataclass
from typing import Any

from simple_safer_server.adapters.command_runner import CommandRunner
from simple_safer_server.core.privileged_actions import PrivilegedActionResult

DEFAULT_HELPER_TIMEOUT_SECONDS = 300


class PrivilegedActionClientError(RuntimeError):
    """Raised when the external privileged helper rejects or fails an action."""

    def __init__(self, message: str, *, exit_code: int | None = None) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class PrivilegedActionClient:
    """Runs allowlisted privileged actions through the `sss-helper` command."""

    command_runner: CommandRunner
    helper_command: tuple[str, ...]
    timeout: float

    def __init__(
        self,
        *,
        command_runner: CommandRunner | None = None,
        helper_command: list[str] | tuple[str, ...] | None = None,
        timeout: float = DEFAULT_HELPER_TIMEOUT_SECONDS,
    ) -> None:
        object.__setattr__(self, "command_runner", command_runner or CommandRunner())
        object.__setattr__(
            self,
            "helper_command",
            tuple(helper_command or default_helper_command()),
        )
        object.__setattr__(self, "timeout", timeout)

    def run(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> PrivilegedActionResult:
        action_payload = payload or {}
        if not isinstance(action_payload, dict):
            raise PrivilegedActionClientError("Privileged action payload must be a JSON object.")

        result = self.command_runner.run(
            [*self.helper_command, "run", action],
            input=json.dumps(action_payload, sort_keys=True),
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "Privileged action failed.").strip()
            raise PrivilegedActionClientError(message, exit_code=result.returncode)

        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise PrivilegedActionClientError("Privileged helper returned invalid JSON.") from exc
        if not isinstance(response, dict):
            raise PrivilegedActionClientError("Privileged helper returned an invalid response.")
        if response.get("action") != action:
            raise PrivilegedActionClientError("Privileged helper returned the wrong action.")
        data = response.get("data")
        if not isinstance(data, dict):
            raise PrivilegedActionClientError("Privileged helper returned invalid action data.")
        return PrivilegedActionResult(action=action, data=data)


def default_helper_command() -> list[str]:
    """Return the helper command for installed systems, tests, and dev runs."""
    configured = os.environ.get("SSS_HELPER_COMMAND")
    if configured:
        return shlex.split(configured)
    helper_path = shutil.which("sss-helper")
    if helper_path:
        sudo_path = shutil.which("sudo")
        if hasattr(os, "geteuid") and os.geteuid() != 0 and sudo_path:
            return [sudo_path, "-n", helper_path]
        return [helper_path]
    return [sys.executable, "-m", "simple_safer_server.privileged_helper"]
