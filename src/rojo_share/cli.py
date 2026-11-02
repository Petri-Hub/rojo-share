"""Command-line entry point for sharing one Rojo session."""

import asyncio
import re
from pathlib import Path
from typing import Annotated

import typer

from rojo_share.session import SessionError, serve

DURATION = re.compile(r"^(\d+)(s|m|h)$")
SECONDS_PER_UNIT = {"s": 1, "m": 60, "h": 3600}

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Share a Rojo development session through a temporary tunnel."""


@app.command("serve")
def serve_command(
    project: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            resolve_path=True,
            help="Rojo project file, such as default.project.json.",
        ),
    ],
    rojo_port: Annotated[
        int,
        typer.Option(
            min=1,
            max=65535,
            metavar="PORT",
            help="Local port for the Rojo server.",
        ),
    ] = 34872,
    duration: Annotated[
        str,
        typer.Option(help="Maximum session lifetime, such as 30s, 5m, or 1h."),
    ] = "1h",
    heartbeat: Annotated[
        str,
        typer.Option(help="WebSocket ping period, such as 10s, 30s, or 1m."),
    ] = "30s",
) -> None:
    """Share one Rojo project."""
    duration_value = duration_seconds(duration)
    heartbeat_value = duration_seconds(heartbeat)
    try:
        asyncio.run(serve(project, rojo_port, duration_value, heartbeat_value))
    except KeyboardInterrupt:
        typer.echo("Session stopped")
    except (SessionError, OSError) as error:
        typer.echo(f"rojo-share: {error}", err=True)
        raise typer.Exit(1) from error


def duration_seconds(value: str) -> int:
    match = DURATION.fullmatch(value)
    if match is None or int(match.group(1)) == 0:
        raise typer.BadParameter("use a positive duration such as 30s, 5m, or 1h")
    return int(match.group(1)) * SECONDS_PER_UNIT[match.group(2)]


if __name__ == "__main__":
    app()
