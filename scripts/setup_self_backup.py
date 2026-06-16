#!/usr/bin/env python3

import argparse
import json
import logging
import sys
from pathlib import Path


def _add_app_to_path() -> None:
    script_path = Path(__file__).resolve()
    candidates = [script_path.parents[1], Path("/opt/SimpleSaferServer")]
    for candidate in candidates:
        if (candidate / "simple_safer_server").is_dir():
            sys.path.insert(0, str(candidate))
            return


try:
    from simple_safer_server.services.config_manager import ConfigManager
    from simple_safer_server.services.runtime import get_runtime
    from simple_safer_server.services.setup_self_backup import (
        DEFAULT_RETENTION_COUNT,
        SetupSelfBackupError,
        SetupSelfBackupService,
    )
except ImportError:
    _add_app_to_path()
    from simple_safer_server.services.config_manager import ConfigManager
    from simple_safer_server.services.runtime import get_runtime
    from simple_safer_server.services.setup_self_backup import (
        DEFAULT_RETENTION_COUNT,
        SetupSelfBackupError,
        SetupSelfBackupService,
    )


def _service() -> SetupSelfBackupService:
    runtime = get_runtime()
    return SetupSelfBackupService(runtime, ConfigManager(runtime=runtime))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create, list, or restore SimpleSaferServer setup self-backups."
    )
    subparsers = parser.add_subparsers(dest="command")

    create = subparsers.add_parser("create", help="Create a self-backup archive.")
    create.add_argument("--destination", help="Mounted backup drive path to write under.")
    create.add_argument(
        "--keep",
        type=int,
        default=DEFAULT_RETENTION_COUNT,
        help=f"Number of newest archives to keep. Default: {DEFAULT_RETENTION_COUNT}.",
    )

    list_parser = subparsers.add_parser("list", help="List self-backup archives.")
    list_parser.add_argument("--destination", help="Mounted backup drive path to inspect.")
    list_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    restore = subparsers.add_parser("restore", help="Restore a self-backup archive.")
    restore.add_argument("archive", help="Archive path to restore.")
    restore.add_argument(
        "--preserve-setup-complete",
        action="store_true",
        help="Keep system.setup_complete exactly as stored in the archive.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()
    command = args.command or "create"
    service = _service()

    if command == "create":
        result = service.create_backup(
            destination=args.destination,
            retention_count=args.keep,
        )
        print(f"Created setup self-backup: {result['archive']}")
        print(f"Files included: {result['file_count']}")
        return 0

    if command == "list":
        backups = service.list_backups(destination=args.destination)
        if args.json:
            print(json.dumps(backups, indent=2))
            return 0
        if not backups:
            print("No setup self-backups found.")
            return 0
        for backup in backups:
            print(f"{backup['name']}  {backup['modified_at']}  {backup['size']} bytes")
        return 0

    if command == "restore":
        result = service.restore_backup(
            args.archive,
            force_setup_incomplete=not args.preserve_setup_complete,
        )
        print(f"Restored setup self-backup: {result['archive']}")
        print(f"Files restored: {len(result['restored'])}")
        if not args.preserve_setup_complete:
            print("system.setup_complete was set to false so setup can reinstall services.")
        return 0

    raise SetupSelfBackupError(f"Unknown command: {command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SetupSelfBackupError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
