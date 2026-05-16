#!/usr/bin/env python3
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


def main() -> int:
    from simple_safer_server.services.app_updates import AppUpdateError, AppUpdateManager

    manager = AppUpdateManager()
    try:
        request = manager.consume_update_request()
        mode = request["mode"]
        before = manager.get_status(fetch_remote=True)
        print(before.get("message") or "Application update status checked.")
        if mode == "cleanup":
            after = manager.force_update_now(stream_to_journal=True)
            print(after.get("message") or "Application cleanup update completed.")
            return 0
        if mode == "switch_branch":
            branch = request.get("branch", "")
            after = manager.switch_branch_now(branch, stream_to_journal=True)
            print(after.get("message") or "Application source switch completed.")
            return 0
        if not before.get("can_update"):
            return 0
        after = manager.update_now(stream_to_journal=True)
        print(after.get("message") or "Application update completed.")
        return 0
    except AppUpdateError as exc:
        print(f"Application update failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
