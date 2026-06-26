from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import TextIO

from simple_safer_server.core.privileged_actions import (
    PrivilegedActionError,
    create_builtin_privileged_action_registry,
    read_json_payload,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sss-helper",
        description="Run allowlisted SimpleSaferServer privileged actions.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    run_parser = subcommands.add_parser("run", help="Run one allowlisted action.")
    run_parser.add_argument("action", help="Action name, such as alerts.write-smtp-config.")

    subcommands.add_parser("list", help="List allowlisted actions.")
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)
    registry = create_builtin_privileged_action_registry()

    if args.command == "list":
        for action in registry.list_actions():
            print(action, file=stdout)
        return 0

    if args.command == "run":
        try:
            payload = read_json_payload(stdin)
            result = registry.run(args.action, payload)
        except KeyError:
            print(f"Unknown privileged action: {args.action}", file=stderr)
            return 2
        except PrivilegedActionError as exc:
            print(str(exc), file=stderr)
            return 2
        except Exception as exc:
            print(f"Privileged action failed: {exc}", file=stderr)
            return 1
        print(json.dumps({"action": result.action, "data": result.data}, sort_keys=True), file=stdout)
        return 0

    parser.error("Unsupported command.")
    return 2


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
