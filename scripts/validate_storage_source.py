#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path


def _add_app_to_path():
    script_path = Path(__file__).resolve()
    candidates = [
        script_path.parents[1],
        Path('/opt/SimpleSaferServer'),
    ]
    for candidate in candidates:
        if (candidate / 'simple_safer_server').exists():
            sys.path.insert(0, str(candidate))
            return


_add_app_to_path()

from simple_safer_server.services.config_manager import ConfigManager  # noqa: E402
from simple_safer_server.services.runtime import get_runtime  # noqa: E402
from simple_safer_server.services.storage_location import (  # noqa: E402
    StorageLocationError,
    validate_storage_ready_for_backup,
)
from simple_safer_server.services.system_utils import SystemUtils  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Verify the cloud backup source folder.")
    parser.add_argument("--source", help="Exact source path that will be passed to rclone")
    args = parser.parse_args()
    runtime = get_runtime()
    config_manager = ConfigManager(runtime=runtime)
    system_utils = SystemUtils(runtime=runtime)
    location = validate_storage_ready_for_backup(
        config_manager,
        system_utils,
        runtime=runtime,
        expected_source=args.source,
    )
    print(f"Storage source verified: {location.path}")


if __name__ == '__main__':
    try:
        main()
    except StorageLocationError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
    except Exception as exc:
        print(f"Storage source validation failed: {exc}", file=sys.stderr)
        sys.exit(1)
