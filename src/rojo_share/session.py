"""Own the Rojo server, proxy, and temporary tunnel as one session."""

import asyncio
import os
import re
import signal
from contextlib import suppress
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout, web

from rojo_share.proxy import create_app

TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com\b")
STARTUP_SECONDS = 45
HEALTH_SECONDS = 20
STOP_SECONDS = 5


class SessionError(Exception):
    """A session could not start or stopped unexpectedly."""


async def _start_process(*command: str, cwd: Path) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )


async def _read_output(
    process: asyncio.subprocess.Process,
    name: str,
    url_found: asyncio.Future[str] | None = None,
) -> None:
    assert process.stdout is not None
    async for raw_line in process.stdout:
        line = raw_line.decode(errors="replace").rstrip()
        if url_found is not None and not url_found.done():
            match = TUNNEL_URL.search(line)
            if match:
                url_found.set_result(match.group())
        if "ERR" in line or "ERROR" in line:
            print(f"[{name}] {line}", flush=True)
    if url_found is not None and not url_found.done():
        url_found.set_exception(SessionError(f"{name} exited before reporting a URL"))


async def _stop_process(process: asyncio.subprocess.Process | None) -> None:
    if process is None or process.returncode is not None:
        return
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        await asyncio.wait_for(process.wait(), STOP_SECONDS)
    except TimeoutError:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        await process.wait()


async def _wait_for_rojo(url: str, rojo: asyncio.subprocess.Process) -> None:
    async with ClientSession(timeout=ClientTimeout(total=5)) as client:
        for _ in range(HEALTH_SECONDS * 2):
            if rojo.returncode is not None:
                raise SessionError(f"Rojo exited with status {rojo.returncode}")
            try:
                async with client.get(f"{url}/api/rojo") as response:
                    if (
                        response.status == 200
                        and response.headers.get("Content-Type")
                        == "application/msgpack"
                    ):
                        return
            except (OSError, TimeoutError):
                pass
            await asyncio.sleep(0.5)
    raise SessionError("Rojo did not become reachable through the tunnel")


async def serve(
    project: Path,
    rojo_port: int,
    duration: float,
    heartbeat: float,
) -> None:
    runner = web.AppRunner(create_app(rojo_port, heartbeat))
    tunnel = None
    rojo = None
    readers: list[asyncio.Task[None]] = []
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    try:
        await site.start()
        proxy_port = runner.addresses[0][1]
        loop = asyncio.get_running_loop()
        url_found: asyncio.Future[str] = loop.create_future()
        tunnel = await _start_process(
            "cloudflared",
            "tunnel",
            "--url",
            f"http://127.0.0.1:{proxy_port}",
            cwd=project.parent,
        )
        readers.append(
            asyncio.create_task(_read_output(tunnel, "cloudflared", url_found))
        )
        try:
            url = await asyncio.wait_for(url_found, STARTUP_SECONDS)
        except TimeoutError as error:
            raise SessionError("cloudflared did not report a URL") from error

        hostname = urlsplit(url).hostname
        rojo = await _start_process(
            "rojo",
            "serve",
            project.name,
            "--address",
            "127.0.0.1",
            "--port",
            str(rojo_port),
            "--allowed-hosts",
            hostname,
            cwd=project.parent,
        )
        readers.append(asyncio.create_task(_read_output(rojo, "rojo")))
        await _wait_for_rojo(url, rojo)
        print(f"Studio URL: {url} (port 443)", flush=True)
        print(f"Session expires in {duration:g} seconds", flush=True)

        done, pending = await asyncio.wait(
            [asyncio.create_task(tunnel.wait()), asyncio.create_task(rojo.wait())],
            timeout=duration,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        for task in pending:
            with suppress(asyncio.CancelledError):
                await task
        if done:
            failed = "cloudflared" if tunnel.returncode is not None else "Rojo"
            raise SessionError(f"{failed} stopped unexpectedly")
        print("Session duration elapsed", flush=True)
    finally:
        await _stop_process(rojo)
        await _stop_process(tunnel)
        for reader in readers:
            with suppress(asyncio.CancelledError):
                await reader
        await runner.cleanup()
