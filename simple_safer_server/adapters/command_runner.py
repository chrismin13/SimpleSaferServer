import subprocess
from typing import Any, List, Optional

DEVNULL = subprocess.DEVNULL
PIPE = subprocess.PIPE
STDOUT = subprocess.STDOUT
CalledProcessError = subprocess.CalledProcessError
SubprocessError = subprocess.SubprocessError
TimeoutExpired = subprocess.TimeoutExpired


class CommandRunner:
    """Runs external commands through a single injectable boundary."""

    def run(
        self,
        command: List[str],
        *,
        capture_output: bool = False,
        check: bool = False,
        input: Optional[Any] = None,
        stdout: Optional[Any] = None,
        stderr: Optional[Any] = None,
        text: bool = False,
        timeout: Optional[float] = None,
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
            timeout=timeout,
        )

    def popen(
        self,
        command: List[str],
        *,
        stdout: Optional[Any] = None,
        stderr: Optional[Any] = None,
        text: bool = False,
        bufsize: int = -1,
        env: Optional[Any] = None,
        start_new_session: bool = False,
    ) -> subprocess.Popen:
        return subprocess.Popen(
            command,
            stdout=stdout,
            stderr=stderr,
            text=text,
            bufsize=bufsize,
            env=env,
            start_new_session=start_new_session,
        )
