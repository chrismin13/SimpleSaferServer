#!/usr/bin/env python3

import argparse
import logging
import sys
from pathlib import Path


def _add_app_to_path():
    script_path = Path(__file__).resolve()
    candidates = [
        script_path.parents[1],
        Path("/opt/SimpleSaferServer"),
    ]
    for candidate in candidates:
        if (candidate / "legacy_migration.py").exists():
            sys.path.insert(0, str(candidate))
            return


_add_app_to_path()

from legacy_migration import MigrationError, import_legacy_bundle  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a legacy SimpleSaferServer installation into the current version."
    )
    parser.add_argument(
        "--bundle-dir",
        required=True,
        help="Directory containing manifest.json, config.conf, msmtprc, and rclone.conf",
    )
    parser.add_argument(
        "--admin-username",
        required=True,
        help="Admin username to create or update in the new installation",
    )
    parser.add_argument(
        "--admin-password-stdin",
        action="store_true",
        help="Read the admin password from stdin",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    if not args.admin_password_stdin:
        raise MigrationError("For safety, --admin-password-stdin is required.")

    admin_password = sys.stdin.readline().rstrip("\r\n")
    if not admin_password:
        raise MigrationError("Admin password was empty.")

    result = import_legacy_bundle(
        args.bundle_dir,
        admin_username=args.admin_username,
        admin_password=admin_password,
    )

    print("Legacy import completed successfully.")
    print(f"Admin user: {result['admin_username']} ({result['admin_action']})")
    print(f"Backup source: {result['mount_point']}")
    print(f"Cloud destination: {result['rclone_dir']}")
    print(f"Normalized backup time: {result['backup_time']}")
    print(f"New-install backups stored in: {result['backup_dir']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MigrationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
