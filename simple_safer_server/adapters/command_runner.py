import subprocess
from typing import Any

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
        command: list[str],
        *,
        capture_output: bool = False,
        check: bool = False,
        input: Any | None = None,
        stdout: Any | None = None,
        stderr: Any | None = None,
        text: bool = False,
        timeout: float | None = None,
        cwd: Any | None = None,
    ) -> subprocess.CompletedProcess:
        # Keep subprocess use centralized so future allowlisting, logging, and
        # fake adapters can be added without changing feature services again.
        kwargs: dict[str, Any] = {
            "capture_output": capture_output,
            "check": check,
            "text": text,
        }
        # subprocess.run rejects capture_output=True when stdout/stderr are present,
        # even if they are None. Only forward stream overrides that callers set.
        if input is not None:
            kwargs["input"] = input
        if stdout is not None:
            kwargs["stdout"] = stdout
        if stderr is not None:
            kwargs["stderr"] = stderr
        if timeout is not None:
            kwargs["timeout"] = timeout
        if cwd is not None:
            kwargs["cwd"] = cwd
        return subprocess.run(command, **kwargs)

    def popen(
        self,
        command: list[str],
        *,
        stdout: Any | None = None,
        stderr: Any | None = None,
        text: bool = False,
        bufsize: int = -1,
        env: Any | None = None,
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
