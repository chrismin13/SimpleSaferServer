#!/usr/bin/env python3
import sys

from simple_safer_server.services.healthchecks import (
    HealthchecksPingError,
    ping_healthchecks_url,
)


def main() -> int:
    url = sys.stdin.read().strip()
    if not url:
        return 0
    try:
        ping_healthchecks_url(url)
    except (HealthchecksPingError, ValueError) as exc:
        print(f"Healthchecks.io success ping failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
