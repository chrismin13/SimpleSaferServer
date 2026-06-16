import configparser
import io
import os
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKUP_ROOT_NAME = "SimpleSaferServer-self-backups"
MANIFEST_NAME = "manifest.json"
ARCHIVE_PREFIX = "setup-self-backup"
DEFAULT_RETENTION_COUNT = 30


class SetupSelfBackupError(Exception):
    """Raised when a setup self-backup cannot be created or restored safely."""


@dataclass(frozen=True)
class BackupItem:
    name: str
    path: Path
    mode: int

    @property
    def archive_name(self) -> str:
        return f"files/{self.name}"


def _atomic_copy_bytes(source: Any, target: Path, *, mode: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=str(target.parent),
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                temp_file.write(chunk)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        temp_path.chmod(mode)
        os.replace(temp_path, target)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _force_setup_incomplete(config_text: str) -> str:
    parser = configparser.ConfigParser()
    parser.read_string(config_text)
    if not parser.has_section("system"):
        parser.add_section("system")
    parser.set("system", "setup_complete", "false")
    stream = io.StringIO()
    parser.write(stream)
    return stream.getvalue()


class SetupSelfBackupService:
    """Back up only SimpleSaferServer-owned setup files, not the whole host."""

    def __init__(self, runtime, config_manager) -> None:
        self.runtime = runtime
        self.config_manager = config_manager

    def _configured_mount_point(self) -> Path:
        mount_point = self.config_manager.get_value(
            "backup",
            "mount_point",
            self.runtime.default_mount_point,
        )
        return Path(str(mount_point or self.runtime.default_mount_point))

    def backup_root(self, destination: Path | str | None = None) -> Path:
        base = Path(destination) if destination is not None else self._configured_mount_point()
        return base / BACKUP_ROOT_NAME

    def _backup_items(self) -> list[BackupItem]:
        config_dir = self.runtime.config_dir
        samba_dir = self.runtime.samba_dir
        candidates = [
            BackupItem("config/config.conf", config_dir / "config.conf", 0o600),
            BackupItem("config/users.json", config_dir / "users.json", 0o600),
            BackupItem("config/.key", config_dir / ".key", 0o600),
            BackupItem("config/.secrets", config_dir / ".secrets", 0o600),
            BackupItem("config/.flask-secret-key", config_dir / ".flask-secret-key", 0o600),
            BackupItem("config/alerts.json", config_dir / "alerts.json", 0o600),
            BackupItem(
                "config/disabled_timers.json", self.runtime.data_dir / "disabled_timers.json", 0o600
            ),
            BackupItem("rclone/rclone.conf", self.runtime.rclone_config_dir / "rclone.conf", 0o600),
            BackupItem("msmtp/msmtprc", self.runtime.msmtp_config_path, 0o600),
            BackupItem(
                "samba/simple_safer_server_globals.conf",
                samba_dir / "simple_safer_server_globals.conf",
                0o644,
            ),
            BackupItem(
                "samba/simple_safer_server_shares.conf",
                samba_dir / "simple_safer_server_shares.conf",
                0o644,
            ),
        ]
        return [item for item in candidates if item.path.is_file()]

    def _ensure_destination_ready(self, backup_root: Path) -> None:
        mount_point = backup_root.parent
        if not self.runtime.is_fake and not mount_point.is_mount():
            raise SetupSelfBackupError(
                f"{mount_point} is not a mounted backup drive. Refusing to write a self-backup there."
            )
        backup_root.mkdir(parents=True, exist_ok=True)

    def create_backup(
        self,
        *,
        destination: Path | str | None = None,
        retention_count: int = DEFAULT_RETENTION_COUNT,
    ) -> dict[str, Any]:
        backup_root = self.backup_root(destination)
        self._ensure_destination_ready(backup_root)
        items = self._backup_items()
        if not items:
            raise SetupSelfBackupError("No setup-owned files were found to back up.")

        created_at = datetime.now(UTC).replace(microsecond=0).isoformat()
        timestamp = created_at.replace("-", "").replace(":", "").replace("+00:00", "Z")
        archive_path = backup_root / f"{ARCHIVE_PREFIX}-{timestamp}.tar.gz"
        manifest = {
            "version": 1,
            "created_at": created_at,
            "note": "This archive contains SimpleSaferServer-owned setup config only. It does not contain /etc/fstab or a whole-system backup.",
            "files": [
                {
                    "name": item.name,
                    "source_path": str(item.path),
                    "mode": oct(item.mode),
                }
                for item in items
            ],
        }

        with tarfile.open(archive_path, "w:gz") as archive:
            manifest_bytes = atomic_json_bytes(manifest)
            manifest_info = tarfile.TarInfo(MANIFEST_NAME)
            manifest_info.size = len(manifest_bytes)
            manifest_info.mtime = int(datetime.now(UTC).timestamp())
            manifest_info.mode = 0o600
            archive.addfile(manifest_info, io.BytesIO(manifest_bytes))
            for item in items:
                archive.add(item.path, arcname=item.archive_name, recursive=False)

        archive_path.chmod(0o600)
        self.prune_old_backups(retention_count=retention_count, backup_root=backup_root)
        return {
            "archive": str(archive_path),
            "created_at": created_at,
            "file_count": len(items),
        }

    def list_backups(self, *, destination: Path | str | None = None) -> list[dict[str, Any]]:
        backup_root = self.backup_root(destination)
        if not backup_root.exists():
            return []
        backups = []
        for archive_path in backup_root.glob(f"{ARCHIVE_PREFIX}-*.tar.gz"):
            backups.append(
                {
                    "archive": str(archive_path),
                    "name": archive_path.name,
                    "size": archive_path.stat().st_size,
                    "modified_at": datetime.fromtimestamp(
                        archive_path.stat().st_mtime,
                        UTC,
                    )
                    .replace(microsecond=0)
                    .isoformat(),
                }
            )
        return sorted(backups, key=lambda item: item["modified_at"], reverse=True)

    def prune_old_backups(
        self,
        *,
        retention_count: int = DEFAULT_RETENTION_COUNT,
        backup_root: Path | None = None,
    ) -> None:
        if retention_count < 1:
            return
        root = backup_root or self.backup_root()
        backups = sorted(
            root.glob(f"{ARCHIVE_PREFIX}-*.tar.gz"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for old_archive in backups[retention_count:]:
            old_archive.unlink(missing_ok=True)

    def resolve_backup_name(self, archive_name: str) -> Path:
        name = Path(str(archive_name or "")).name
        if not name:
            raise SetupSelfBackupError("Backup archive name is required.")
        backup_root = self.backup_root().resolve()
        archive_path = (backup_root / name).resolve()
        if archive_path.parent != backup_root:
            raise SetupSelfBackupError("Backup archive must be inside the self-backup folder.")
        if not archive_path.is_file():
            raise SetupSelfBackupError("Backup archive was not found.")
        return archive_path

    def restore_backup(
        self,
        archive_path: Path | str,
        *,
        force_setup_incomplete: bool = True,
    ) -> dict[str, Any]:
        archive_path = Path(archive_path)
        if not archive_path.is_file():
            raise SetupSelfBackupError("Backup archive was not found.")

        by_name = {item.name: item for item in self._backup_items_for_restore()}
        restored = []
        with tarfile.open(archive_path, "r:gz") as archive:
            manifest_member = archive.getmember(MANIFEST_NAME)
            manifest_file = archive.extractfile(manifest_member)
            if manifest_file is None:
                raise SetupSelfBackupError("Backup archive is missing its manifest.")
            manifest = atomic_json_loads(manifest_file.read())
            if manifest.get("version") != 1:
                raise SetupSelfBackupError("Backup archive version is not supported.")

            for file_info in manifest.get("files", []):
                name = file_info.get("name")
                item = by_name.get(name)
                if item is None:
                    continue
                member_name = f"files/{name}"
                member = archive.getmember(member_name)
                source = archive.extractfile(member)
                if source is None:
                    raise SetupSelfBackupError(f"Backup archive is missing {name}.")
                if name == "config/config.conf" and force_setup_incomplete:
                    config_text = source.read().decode("utf-8")
                    config_text = _force_setup_incomplete(config_text)
                    source = io.BytesIO(config_text.encode("utf-8"))
                _atomic_copy_bytes(source, item.path, mode=item.mode)
                restored.append(name)

        self.runtime.config_dir.mkdir(parents=True, exist_ok=True)
        self.runtime.config_dir.chmod(0o700)
        return {"archive": str(archive_path), "restored": restored}

    def _backup_items_for_restore(self) -> list[BackupItem]:
        config_dir = self.runtime.config_dir
        samba_dir = self.runtime.samba_dir
        return [
            BackupItem("config/config.conf", config_dir / "config.conf", 0o600),
            BackupItem("config/users.json", config_dir / "users.json", 0o600),
            BackupItem("config/.key", config_dir / ".key", 0o600),
            BackupItem("config/.secrets", config_dir / ".secrets", 0o600),
            BackupItem("config/.flask-secret-key", config_dir / ".flask-secret-key", 0o600),
            BackupItem("config/alerts.json", config_dir / "alerts.json", 0o600),
            BackupItem(
                "config/disabled_timers.json", self.runtime.data_dir / "disabled_timers.json", 0o600
            ),
            BackupItem("rclone/rclone.conf", self.runtime.rclone_config_dir / "rclone.conf", 0o600),
            BackupItem("msmtp/msmtprc", self.runtime.msmtp_config_path, 0o600),
            BackupItem(
                "samba/simple_safer_server_globals.conf",
                samba_dir / "simple_safer_server_globals.conf",
                0o644,
            ),
            BackupItem(
                "samba/simple_safer_server_shares.conf",
                samba_dir / "simple_safer_server_shares.conf",
                0o644,
            ),
        ]


def atomic_json_bytes(payload: dict[str, Any]) -> bytes:
    return atomic_json_dumps(payload).encode("utf-8")


def atomic_json_dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, indent=2, sort_keys=True)


def atomic_json_loads(payload: bytes) -> dict[str, Any]:
    import json

    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise SetupSelfBackupError("Backup manifest is invalid.")
    return data
