#!/usr/bin/env python3

"""Import bundles produced by https://github.com/chrismin13/SimpleSaferServer-old."""

import argparse
import logging
import sys
from pathlib import Path


def _add_app_to_path():
    script_path = Path(__file__).resolve()
    # Prefer the checkout path for development, then the installed /opt path used
    # by production installs that run this script from /usr/local/bin.
    candidates = [
        script_path.parents[1],
        Path("/opt/SimpleSaferServer"),
    ]
    for candidate in candidates:
        # A directory check avoids treating a stray file as the application package.
        if (candidate / "simple_safer_server").is_dir():
            # The legacy importer lives in the app package, so sys.path must be
            # patched before the intentionally delayed import below.
            sys.path.insert(0, str(candidate))
            return
    print(
        "WARNING: neither candidate path contained the simple_safer_server package; "
        "check the working directory or install location.",
        file=sys.stderr,
    )


_add_app_to_path()

# The E402 suppression is intentional because _add_app_to_path() must run before importing the package.
from simple_safer_server.legacy.migration import MigrationError, import_legacy_bundle  # noqa: E402


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
        # The import command is often run from shell history; stdin keeps the
        # temporary admin password out of argv and process listings.
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
        # Propagate main()'s return code as the process exit status.
        raise SystemExit(main())
    except MigrationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
