import argparse
import os
import sys

from simple_safer_server.wsgi import app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SimpleSaferServer Flask app.")
    parser.add_argument(
        "--host",
        # The admin UI must be reachable on headless home servers.
        default="0.0.0.0",
        help="Host to listen on (default: 0.0.0.0)",
    )
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on (default: 5000)")
    parser.add_argument("--debug", dest="debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--no-debug", dest="debug", action="store_false", help="Disable debug mode")
    parser.set_defaults(debug=False)
    args = parser.parse_args()
    if args.debug and hasattr(os, "geteuid") and os.geteuid() == 0:
        print(
            "WARNING: Flask debug mode is dangerous when SimpleSaferServer runs as root; "
            "disable debug mode unless this is an isolated development session.",
            file=sys.stderr,
        )
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
