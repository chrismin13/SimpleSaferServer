from typing import Optional

from simple_safer_server.adapters.command_runner import (
    CalledProcessError,
    CommandRunner,
    TimeoutExpired,
)

# A spun-down USB HDD can take a while to wake, especially through an adapter or dock.
# These probes run in background health paths, so favor avoiding false timeout
# failures over making the check feel instant.
BLKID_TIMEOUT_SECONDS = 15
HDSENTINEL_TIMEOUT_SECONDS = 45
SMARTCTL_TIMEOUT_SECONDS = 60


class DriveHealthCommandAdapter:
    """Wraps SMART, HDSentinel, and alert email commands."""

    def __init__(self, command_runner: Optional[CommandRunner] = None) -> None:
        self._command_runner = command_runner or CommandRunner()

    def smartctl_help(self):
        return self._command_runner.run(
            ["smartctl", "-h"],
            capture_output=True,
            text=True,
            timeout=SMARTCTL_TIMEOUT_SECONDS,
        )

    def find_device_by_uuid(self, uuid: str):
        return self._command_runner.run(
            ["blkid", "-t", f"UUID={uuid}", "-o", "device"],
            capture_output=True,
            text=True,
            timeout=BLKID_TIMEOUT_SECONDS,
        )

    def smartctl_attributes(self, command):
        return self._command_runner.run(
            command,
            capture_output=True,
            text=True,
            timeout=SMARTCTL_TIMEOUT_SECONDS,
        )

    def hdsentinel(self, command):
        return self._command_runner.run(
            command,
            capture_output=True,
            text=True,
            timeout=HDSENTINEL_TIMEOUT_SECONDS,
        )

    def send_email(self, from_address: str, email_address: str, email_body: str) -> None:
        self._command_runner.run(
            ["msmtp", f"--from={from_address}", email_address],
            input=email_body,
            text=True,
            check=True,
        )


__all__ = ["CalledProcessError", "DriveHealthCommandAdapter", "TimeoutExpired"]
