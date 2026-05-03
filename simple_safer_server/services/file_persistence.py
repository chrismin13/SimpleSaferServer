import fcntl
import json
import os
import tempfile
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, Callable, Iterator, Optional


def _fsync_directory(path: Path) -> None:
    directory_fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def atomic_write_text(
    path: Path,
    content: str,
    *,
    mode: Optional[int] = None,
    encoding: str = "utf-8",
    durable: bool = True,
) -> None:
    """Publish text with a same-directory temp file and atomic replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding=encoding,
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(content)
            temp_file.flush()
            if durable:
                os.fsync(temp_file.fileno())

        if mode is not None:
            temp_path.chmod(mode)

        os.replace(str(temp_path), str(path))
        temp_path = None
        if durable:
            _fsync_directory(path.parent)
    finally:
        if temp_path is not None:
            with suppress(OSError):
                temp_path.unlink()


def atomic_write_json(
    path: Path,
    payload: Any,
    *,
    mode: Optional[int] = None,
    durable: bool = True,
    indent: int = 2,
) -> None:
    atomic_write_text(
        path,
        json.dumps(payload, indent=indent),
        mode=mode,
        durable=durable,
    )


@contextmanager
def locked_path(lock_path: Path, *, mode: Optional[int] = None) -> Iterator[None]:
    """Hold an exclusive flock on a stable sidecar path."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock_file:
        if mode is not None:
            lock_path.chmod(mode)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def read_json(path: Path, default: Any) -> Any:
    try:
        data = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return default
    if not data:
        return default
    return json.loads(data)


def locked_json_update(
    path: Path,
    lock_path: Path,
    default: Any,
    update_fn: Callable[[Any], Any],
    *,
    file_mode: Optional[int] = None,
    lock_mode: Optional[int] = None,
    durable: bool = True,
) -> Any:
    """Serialize read/modify/write JSON updates across processes."""
    with locked_path(lock_path, mode=lock_mode):
        current = read_json(path, default)
        updated = update_fn(current)
        atomic_write_json(path, updated, mode=file_mode, durable=durable)
        return updated
