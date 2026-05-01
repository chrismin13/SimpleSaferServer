import subprocess
from typing import Any, Dict, List, Optional

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
        kwargs: Dict[str, Any] = {
            "capture_output": capture_output,
            "check": check,
            "text": text,
        }
        # Python 3.7 rejects capture_output=True when stdout/stderr are present,
        # even if they are None. Only forward stream overrides that callers set.
        if input is not None:
            kwargs["input"] = input
        if stdout is not None:
            kwargs["stdout"] = stdout
        if stderr is not None:
            kwargs["stderr"] = stderr
        if timeout is not None:
            kwargs["timeout"] = timeout
        return subprocess.run(command, **kwargs)

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
