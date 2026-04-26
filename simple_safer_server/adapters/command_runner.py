import subprocess
from typing import Any, List, Optional

PIPE = subprocess.PIPE


class CommandRunner:
    """Runs external commands through a single injectable boundary."""

    def run(
        self,
        command: List[str],
        *,
        capture_output: bool = False,
        check: bool = False,
        input: Optional[str] = None,
        stdout: Optional[Any] = None,
        stderr: Optional[Any] = None,
        text: bool = False,
    ) -> subprocess.CompletedProcess:
        # Keep subprocess use centralized so future allowlisting, logging, and
        # fake adapters can be added without changing feature services again.
        return subprocess.run(
            command,
            capture_output=capture_output,
            check=check,
            input=input,
            stdout=stdout,
            stderr=stderr,
            text=text,
        )
