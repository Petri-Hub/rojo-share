"""Command-line entry point for sharing one Rojo session."""

import argparse
import asyncio
import re
from pathlib import Path

from rojo_share.session import SessionError, serve

DURATION = re.compile(r"^(\d+)(s|m|h)$")
SECONDS_PER_UNIT = {"s": 1, "m": 60, "h": 3600}


def duration_seconds(value: str) -> float:
    match = DURATION.fullmatch(value)
    if match is None or int(match.group(1)) == 0:
        raise argparse.ArgumentTypeError(
            "use a positive duration such as 30s, 5m, or 1h"
        )
    return int(match.group(1)) * SECONDS_PER_UNIT[match.group(2)]


def main() -> int:
    parser = argparse.ArgumentParser(prog="rojo-share")
    commands = parser.add_subparsers(dest="command", required=True)
    serve_command = commands.add_parser("serve", help="share one Rojo project")
    serve_command.add_argument("project", type=Path)
    serve_command.add_argument("--rojo-port", type=int, default=34872)
    serve_command.add_argument("--duration", type=duration_seconds, default=3600.0)
    serve_command.add_argument("--heartbeat", type=duration_seconds, default=30.0)
    args = parser.parse_args()
    project = args.project.resolve()
    if not project.is_file():
        parser.error(f"project file does not exist: {project}")
    if not 1 <= args.rojo_port <= 65535:
        parser.error("--rojo-port must be between 1 and 65535")
    try:
        asyncio.run(serve(project, args.rojo_port, args.duration, args.heartbeat))
    except KeyboardInterrupt:
        print("Session stopped")
    except (SessionError, OSError) as error:
        parser.exit(1, f"rojo-share: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
