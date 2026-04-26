import os
import signal
from pathlib import Path
from typing import Optional

from simple_safer_server.adapters.command_runner import (
    DEVNULL,
    PIPE,
    STDOUT,
    CommandRunner,
    TimeoutExpired,
)


class SystemUpdatesCommandAdapter:
    """Wraps package-manager support commands outside the long-running apt worker."""

    def __init__(self, command_runner: Optional[CommandRunner] = None) -> None:
        self._command_runner = command_runner or CommandRunner()

    def is_lock_held(self, fuser_binary: str, path: Path) -> bool:
        result = self._command_runner.run(
            [fuser_binary, str(path)],
            stdout=DEVNULL,
            stderr=DEVNULL,
        )
        return result.returncode == 0

    def remove_files(self, paths):
        return self._command_runner.run(
            ["sudo", "rm", "-f", *paths],
            check=True,
            capture_output=True,
            text=True,
        )

    def start_apt_operation(self, command, env):
        return self._command_runner.popen(
            command,
            stdout=PIPE,
            stderr=STDOUT,
            text=True,
            bufsize=1,
            env=env,
            # Keep apt in its own session so Stop can terminate the whole
            # process group without using preexec_fn in Flask's threaded process.
            start_new_session=True,
        )

    def terminate_process(self, proc) -> None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            proc.terminate()
        try:
            proc.wait(timeout=10)
        except TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()

    def write_apt_periodic_config(self, temp_file):
        return self._command_runner.run(
            ["sudo", "tee", "/etc/apt/apt.conf.d/20auto-upgrades"],
            input=temp_file.read(),
            stdout=DEVNULL,
            stderr=PIPE,
            text=True,
            check=True,
        )

    def livepatch_status_json(self, binary: str):
        return self._command_runner.run(
            [binary, "status", "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
        )

    def livepatch_status_text(self, binary: str):
        return self._command_runner.run(
            [binary, "status"],
            capture_output=True,
            text=True,
            check=False,
        )

    def pro_attach(self, pro_binary: str, attach_config_path: Path):
        return self._command_runner.run(
            ["sudo", pro_binary, "attach", "--attach-config", str(attach_config_path)],
            check=False,
            capture_output=True,
            text=True,
        )

    def pro_enable_livepatch(self, pro_binary: str):
        return self._command_runner.run(
            ["sudo", pro_binary, "enable", "livepatch"],
            check=True,
            capture_output=True,
            text=True,
        )
