import json
import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from simple_safer_server.adapters.command_runner import CommandRunner
from simple_safer_server.modules.storage.backup_drive_setup import apply_backup_drive_configuration
from simple_safer_server.services.file_persistence import atomic_write_json, atomic_write_text
from simple_safer_server.services.runtime import get_fake_state, get_runtime
from simple_safer_server.web.problems import OperationProblem

STORAGE_SECTION = "storage"
MODE_MANAGED_DRIVE = "managed_drive"
MODE_EXISTING_FOLDER = "existing_folder"
STORAGE_MARKER_DIR_NAME = ".simple-safer-server"
STORAGE_MARKER_FILE_NAME = "storage.json"
PROBE_FILE_NAME = ".probe.tmp"
LOGGER = logging.getLogger(__name__)


class StorageLocationError(Exception):
    """Raised when the configured storage location cannot be trusted."""


@dataclass(frozen=True)
class StorageLocation:
    path: str
    mode: str
    storage_id: str
    mount_source: str
    mount_target: str
    mount_fstype: str

    @property
    def app_manages_mount(self) -> bool:
        return self.mode == MODE_MANAGED_DRIVE


ROOT_PATH = Path("/")
UNSAFE_STORAGE_PATHS = {
    ROOT_PATH / "bin",
    ROOT_PATH / "boot",
    ROOT_PATH / "dev",
    ROOT_PATH / "etc",
    ROOT_PATH / "home",
    ROOT_PATH / "lib",
    ROOT_PATH / "lib64",
    ROOT_PATH / "opt",
    ROOT_PATH / "proc",
    ROOT_PATH / "root",
    ROOT_PATH / "run",
    ROOT_PATH / "sbin",
    ROOT_PATH / "sys",
    ROOT_PATH / "tmp",
    ROOT_PATH / "usr",
    ROOT_PATH / "var",
}


def _storage_id() -> str:
    return secrets.token_urlsafe(24)


def _storage_section(config_manager: Any) -> dict[str, str]:
    if not hasattr(config_manager, "get_all_config"):
        return {}
    return config_manager.get_all_config().get(STORAGE_SECTION, {})


def get_storage_location(config_manager: Any, runtime: Any | None = None) -> StorageLocation:
    runtime = runtime or get_runtime()
    storage = _storage_section(config_manager)
    if hasattr(config_manager, "get_all_config"):
        backup = config_manager.get_all_config().get("backup", {})
    else:
        backup = {
            "mount_point": config_manager.get_value(
                "backup", "mount_point", runtime.default_mount_point
            ),
            "uuid": config_manager.get_value("backup", "uuid", ""),
        }
    mode = storage.get("mode") or (
        MODE_MANAGED_DRIVE if backup.get("uuid") else MODE_EXISTING_FOLDER
    )
    if mode not in {MODE_MANAGED_DRIVE, MODE_EXISTING_FOLDER}:
        mode = MODE_EXISTING_FOLDER
    path = storage.get("path") or backup.get("mount_point") or runtime.default_mount_point
    return StorageLocation(
        path=path,
        mode=mode,
        storage_id=storage.get("storage_id", ""),
        mount_source=storage.get("mount_source", ""),
        mount_target=storage.get("mount_target", ""),
        mount_fstype=storage.get("mount_fstype", ""),
    )


def _set_storage_config(
    config_manager: Any,
    *,
    path: str,
    mode: str,
    storage_id: str,
    mount_source: str = "",
    mount_target: str = "",
    mount_fstype: str = "",
) -> None:
    config_manager.set_value(STORAGE_SECTION, "mode", mode)
    config_manager.set_value(STORAGE_SECTION, "path", path)
    config_manager.set_value(STORAGE_SECTION, "storage_id", storage_id)
    config_manager.set_value(STORAGE_SECTION, "mount_source", mount_source)
    config_manager.set_value(STORAGE_SECTION, "mount_target", mount_target)
    config_manager.set_value(STORAGE_SECTION, "mount_fstype", mount_fstype)
    # Scripts and dashboard mount actions still read backup.mount_point, so keep
    # the selected storage path in both sections until those callers share one
    # storage contract.
    config_manager.set_value("backup", "mount_point", path)


def save_storage_location(config_manager: Any, location: StorageLocation) -> None:
    """Persist one already-validated storage location into app config."""
    _set_storage_config(
        config_manager,
        path=location.path,
        mode=location.mode,
        storage_id=location.storage_id,
        mount_source=location.mount_source,
        mount_target=location.mount_target,
        mount_fstype=location.mount_fstype,
    )


def refresh_storage_task_config(config_manager: Any, system_utils: Any) -> None:
    """Validate worker schedule config after a storage source change."""
    config = config_manager.get_all_config()
    ok, error = system_utils.validate_worker_task_config(config)
    if not ok:
        raise OperationProblem(
            f"Storage was saved, but worker schedule config was not valid: {error}"
        )


def _normalize_storage_path(path: str | os.PathLike[str] | None) -> Path:
    if path is None:
        raise StorageLocationError("Storage location is required.")
    if isinstance(path, os.PathLike):
        path = os.fspath(path)
    if not isinstance(path, str):
        raise StorageLocationError("Storage location must be a text path.")

    text = path.strip()
    if not text:
        raise StorageLocationError("Storage location is required.")
    expanded = Path(text).expanduser()
    # Check the path the admin actually entered before resolve() turns a
    # relative path into an absolute path based on the current working directory.
    if not expanded.is_absolute():
        raise StorageLocationError("Storage location must be an absolute path.")
    return expanded.resolve()


def validate_existing_folder_path(path: str, runtime: Any | None = None) -> Path:
    runtime = runtime or get_runtime()
    resolved = _normalize_storage_path(path)
    # "/" must be rejected exactly. It cannot live in UNSAFE_STORAGE_PATHS because
    # every absolute path has "/" as a parent.
    if resolved == ROOT_PATH:
        raise StorageLocationError(
            f"Do not use {resolved} as storage. Choose a dedicated storage folder."
        )
    blocked = set() if runtime.is_fake else {path.resolve() for path in UNSAFE_STORAGE_PATHS}
    blocked.update(
        {
            runtime.config_dir.resolve(),
            runtime.data_dir.resolve(),
            runtime.logs_dir.resolve(),
            runtime.volatile_dir.resolve(),
            runtime.repo_root.resolve(),
        }
    )
    for blocked_path in blocked:
        if resolved == blocked_path or blocked_path in resolved.parents:
            raise StorageLocationError(
                f"Do not use {resolved} as storage. Choose a dedicated storage folder."
            )
    if not resolved.exists():
        raise StorageLocationError("Storage folder does not exist.")
    if not resolved.is_dir():
        raise StorageLocationError("Storage location must be a folder.")
    if not os.access(resolved, os.R_OK | os.W_OK | os.X_OK):
        raise StorageLocationError("Storage folder must be readable and writable.")
    return resolved


def marker_dir(path: str | Path) -> Path:
    return Path(path) / STORAGE_MARKER_DIR_NAME


def marker_path(path: str | Path) -> Path:
    return marker_dir(path) / STORAGE_MARKER_FILE_NAME


def _write_storage_marker(path: str | Path, storage_id: str) -> None:
    marker = marker_path(path)
    atomic_write_json(
        marker,
        {
            "storage_id": storage_id,
            "managed_by": "SimpleSaferServer",
            "purpose": "cloud backup source safety check",
        },
        mode=0o600,
    )


def _read_storage_marker(path: str | Path) -> dict[str, Any]:
    marker = marker_path(path)
    try:
        marker_text = marker.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise StorageLocationError(
            f"Storage marker is missing at {marker}. "
            "If this is the correct storage folder, repair the marker."
        ) from exc
    except Exception as exc:
        raise StorageLocationError(f"Could not read storage marker at {marker}: {exc}") from exc
    try:
        return json.loads(marker_text)
    except json.JSONDecodeError as exc:
        raise StorageLocationError(
            f"Storage marker at {marker} is broken. "
            "If this is the correct storage folder, repair the marker."
        ) from exc


def _probe_storage_write(path: str | Path) -> None:
    probe_path = marker_dir(path) / PROBE_FILE_NAME
    token = _storage_id()
    try:
        atomic_write_text(probe_path, token, mode=0o600)
        if probe_path.read_text(encoding="utf-8") != token:
            raise StorageLocationError("Storage write probe could not read back the same value.")
    except StorageLocationError:
        raise
    except Exception as exc:
        raise StorageLocationError(f"Storage write probe failed at {probe_path}: {exc}") from exc
    finally:
        try:
            probe_path.unlink()
        except FileNotFoundError:
            pass
        except Exception as exc:
            raise StorageLocationError(
                f"Storage write probe succeeded but the temporary file could not be deleted: {exc}"
            ) from exc


def _detect_mount_identity(
    path: Path, command_runner: CommandRunner | None = None
) -> dict[str, str]:
    runner = command_runner or CommandRunner()
    try:
        result = runner.run(
            ["findmnt", "-T", str(path), "-n", "-o", "SOURCE,TARGET,FSTYPE"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except Exception:
        return {}
    if result.returncode != 0:
        return {}
    parts = (result.stdout or "").strip().split(None, 2)
    if len(parts) != 3:
        return {}
    return {"mount_source": parts[0], "mount_target": parts[1], "mount_fstype": parts[2]}


def _run_mount_lookup(command: list[str], command_runner: CommandRunner | None = None) -> str:
    runner = command_runner or CommandRunner()
    try:
        result = runner.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except Exception as exc:
        raise StorageLocationError(f"Could not verify the mounted storage drive: {exc}") from exc
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def _mounted_uuid_for_path(path: Path, command_runner: CommandRunner | None = None) -> str:
    uuid = _run_mount_lookup(
        ["findmnt", "-T", str(path), "-n", "-o", "UUID"],
        command_runner=command_runner,
    )
    if uuid:
        return uuid

    source = _run_mount_lookup(
        ["findmnt", "-T", str(path), "-n", "-o", "SOURCE"],
        command_runner=command_runner,
    )
    if not source:
        return ""
    return _run_mount_lookup(
        ["blkid", "-s", "UUID", "-o", "value", source],
        command_runner=command_runner,
    )


def _fake_mounted_uuid(runtime: Any, storage_path: Path) -> str:
    if not getattr(runtime, "is_fake", False) or not hasattr(runtime, "state_path"):
        return ""
    fake_state = get_fake_state(runtime)
    state = fake_state.load()
    if Path(str(state.get("mount_point", ""))).resolve() != storage_path.resolve():
        return ""
    return str(state.get("uuid", "")).strip()


def _verify_managed_drive_uuid(
    config_manager: Any,
    system_utils: Any,
    storage_path: Path,
    command_runner: CommandRunner | None = None,
    runtime: Any | None = None,
) -> None:
    expected_uuid = str(config_manager.get_value("backup", "uuid", "")).strip()
    if not expected_uuid:
        raise StorageLocationError(
            "Managed drive UUID is missing from the app configuration. "
            "Choose the managed drive again below."
        )
    if not system_utils.is_mounted(str(storage_path)):
        raise StorageLocationError(f"The managed storage drive is not mounted at {storage_path}.")

    # Fake mode simulates a mounted backup drive with FakeState. Using host
    # findmnt here would compare the configured fake UUID against the developer
    # machine's real filesystem UUID and make the safety check fail forever.
    actual_uuid = _fake_mounted_uuid(runtime, storage_path) if runtime else ""
    if not actual_uuid:
        actual_uuid = _mounted_uuid_for_path(storage_path, command_runner=command_runner)
    if not actual_uuid:
        raise StorageLocationError(
            f"Could not verify which drive is mounted at {storage_path}. Cloud backup will not run."
        )
    if actual_uuid.lower() != expected_uuid.lower():
        raise StorageLocationError(
            "The drive mounted at the storage location does not match the configured drive UUID."
        )


def _verify_mount_identity(
    location: StorageLocation, command_runner: CommandRunner | None = None
) -> None:
    if not location.mount_source or not location.mount_target or not location.mount_fstype:
        return
    current = _detect_mount_identity(Path(location.path), command_runner=command_runner)
    expected = {
        "mount_source": location.mount_source,
        "mount_target": location.mount_target,
        "mount_fstype": location.mount_fstype,
    }
    if current != expected:
        raise StorageLocationError(
            "Storage folder is on a different mounted filesystem now. "
            "Choose the storage target again if this change was intentional."
        )


def configure_existing_folder(
    config_manager: Any,
    path: str,
    runtime: Any | None = None,
    command_runner: CommandRunner | None = None,
) -> StorageLocation:
    location = prepare_existing_folder(path, runtime=runtime, command_runner=command_runner)
    save_storage_location(config_manager, location)
    return get_storage_location(config_manager, runtime=runtime)


def prepare_existing_folder(
    path: str,
    runtime: Any | None = None,
    command_runner: CommandRunner | None = None,
) -> StorageLocation:
    """Validate a folder and write its marker without changing app config."""
    runtime = runtime or get_runtime()
    resolved = validate_existing_folder_path(path, runtime=runtime)
    storage_id = _storage_id()
    marker_dir(resolved).mkdir(mode=0o700, exist_ok=True)
    _write_storage_marker(resolved, storage_id)
    _probe_storage_write(resolved)
    mount_identity = _detect_mount_identity(resolved, command_runner=command_runner)
    return StorageLocation(
        path=str(resolved),
        mode=MODE_EXISTING_FOLDER,
        storage_id=storage_id,
        mount_source=mount_identity.get("mount_source", ""),
        mount_target=mount_identity.get("mount_target", ""),
        mount_fstype=mount_identity.get("mount_fstype", ""),
    )


def mark_managed_drive_storage(
    config_manager: Any,
    path: str,
    runtime: Any | None = None,
) -> StorageLocation:
    runtime = runtime or get_runtime()
    resolved = _normalize_storage_path(path)
    resolved.mkdir(parents=True, exist_ok=True)
    storage_id = get_storage_location(config_manager, runtime=runtime).storage_id or _storage_id()
    marker_dir(resolved).mkdir(mode=0o700, exist_ok=True)
    _write_storage_marker(resolved, storage_id)
    _probe_storage_write(resolved)
    _set_storage_config(
        config_manager,
        path=str(resolved),
        mode=MODE_MANAGED_DRIVE,
        storage_id=storage_id,
    )
    return get_storage_location(config_manager, runtime=runtime)


def configure_managed_drive_storage(
    *,
    partition: str,
    mount_point: str,
    config_manager: Any,
    smb_manager: Any,
    system_utils: Any,
    runtime: Any | None = None,
    command_adapter: Any | None = None,
    ntfs_driver: str = "ntfs-3g",
) -> dict[str, Any]:
    """Switch to a managed drive and finish storage safety setup as one action."""
    runtime = runtime or get_runtime()
    previous_location = get_storage_location(config_manager, runtime=runtime)

    def finish_storage_setup(result: dict[str, Any]) -> None:
        mark_managed_drive_storage(
            config_manager,
            result.get("mount_point", mount_point),
            runtime=runtime,
        )
        refresh_storage_task_config(config_manager, system_utils)

    try:
        return apply_backup_drive_configuration(
            partition=partition,
            mount_point=mount_point,
            auto_mount=True,
            config_manager=config_manager,
            smb_manager=smb_manager,
            runtime=runtime,
            command_adapter=command_adapter,
            ntfs_driver=ntfs_driver,
            post_configure=finish_storage_setup,
        )
    except Exception:
        try:
            save_storage_location(config_manager, previous_location)
        except Exception:
            LOGGER.exception("Could not restore previous storage location after drive setup failure")
        raise


def repair_storage_marker(config_manager: Any, runtime: Any | None = None) -> StorageLocation:
    runtime = runtime or get_runtime()
    location = get_storage_location(config_manager, runtime=runtime)
    if not location.storage_id:
        raise StorageLocationError(
            "Storage ID is missing from the app configuration. "
            "Choose a storage target below to create a new one."
        )
    storage_path = _normalize_storage_path(location.path)
    marker_dir(storage_path).mkdir(mode=0o700, exist_ok=True)
    _write_storage_marker(storage_path, location.storage_id)
    _probe_storage_write(storage_path)
    return location


def validate_storage_ready_for_backup(
    config_manager: Any,
    system_utils: Any,
    runtime: Any | None = None,
    command_runner: CommandRunner | None = None,
) -> StorageLocation:
    runtime = runtime or get_runtime()
    location = get_storage_location(config_manager, runtime=runtime)
    storage_path = _normalize_storage_path(location.path)
    if not storage_path.exists() or not storage_path.is_dir():
        raise StorageLocationError(f"Storage location is not available: {storage_path}")

    marker = _read_storage_marker(storage_path)
    if not location.storage_id:
        raise StorageLocationError(
            "Storage ID is missing from the app configuration. "
            "Choose a storage target below to create a new one."
        )
    if marker.get("storage_id") != location.storage_id:
        raise StorageLocationError(
            "Storage marker does not match the app configuration. "
            "Confirm this is the correct storage folder before repairing it."
        )
    _probe_storage_write(storage_path)

    if location.mode == MODE_MANAGED_DRIVE:
        _verify_managed_drive_uuid(
            config_manager,
            system_utils,
            storage_path,
            command_runner=command_runner,
            runtime=runtime,
        )
    else:
        _verify_mount_identity(location, command_runner=command_runner)
    return location


def storage_status(
    config_manager: Any,
    system_utils: Any,
    runtime: Any | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    try:
        location = validate_storage_ready_for_backup(
            config_manager,
            system_utils,
            runtime=runtime,
            command_runner=command_runner,
        )
        return {"checked": True, "ok": True, "error": "", "location": location}
    except StorageLocationError as exc:
        location = get_storage_location(config_manager, runtime=runtime)
        return {"checked": True, "ok": False, "error": str(exc), "location": location}


def passive_storage_status(
    config_manager: Any,
    system_utils: Any,
    runtime: Any | None = None,
) -> dict[str, Any]:
    """Return display status without reading from or writing to the storage path."""
    runtime = runtime or get_runtime()
    location = get_storage_location(config_manager, runtime=runtime)
    if location.mode == MODE_MANAGED_DRIVE:
        mounted = system_utils.is_mounted(location.path)
        return {
            "checked": False,
            "ok": mounted,
            "error": ""
            if mounted
            else f"The managed storage drive is not mounted at {location.path}.",
            "location": location,
        }
    return {
        "checked": False,
        "ok": True,
        "error": "",
        "location": location,
    }
