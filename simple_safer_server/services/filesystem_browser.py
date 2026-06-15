import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LocalPathEntry:
    name: str
    type: str


@dataclass(frozen=True)
class LocalPathList:
    path: str
    parent: str | None
    dirs: list[str]
    files: list[str]
    entries: list[LocalPathEntry]


def list_local_path(path: str | None) -> LocalPathList:
    """List one local filesystem path for admin-facing folder pickers."""
    if path is not None and not isinstance(path, str):
        raise NotADirectoryError("Not a directory.")
    resolved_path = os.path.abspath(path or "/")
    if not os.path.isdir(resolved_path):
        raise NotADirectoryError("Not a directory.")

    entries: list[LocalPathEntry] = []
    with os.scandir(resolved_path) as scan:
        for entry in scan:
            try:
                entry_type = "folder" if entry.is_dir() else "file"
            except OSError:
                # A path can change while the picker is reading it. Showing the
                # entry as a file keeps the rest of the folder usable.
                entry_type = "file"
            entries.append(LocalPathEntry(name=entry.name, type=entry_type))

    entries.sort(key=lambda item: (item.type != "folder", item.name.casefold()))
    dirs = [entry.name for entry in entries if entry.type == "folder"]
    files = [entry.name for entry in entries if entry.type == "file"]
    parent = os.path.dirname(resolved_path) if resolved_path != "/" else None
    return LocalPathList(
        path=resolved_path,
        parent=parent,
        dirs=dirs,
        files=files,
        entries=entries,
    )
