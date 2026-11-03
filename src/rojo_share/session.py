"""Own the Rojo server, proxy, and temporary tunnel as one session."""

import asyncio
import os
import re
import shutil
import signal
from contextlib import suppress
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout, web

from rojo_share.proxy import create_app

TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com\b")
DOH_URL = "https://1.1.1.1/dns-query"
STARTUP_SECONDS = 45
DNS_SECONDS = 20
READY_SECONDS = 120
PROGRESS_SECONDS = 10
STOP_SECONDS = 5


class SessionError(Exception):
    """A session could not start or stopped unexpectedly."""


async def _start_process(*command: str, cwd: Path) -> asyncio.subprocess.Process:
    if shutil.which(command[0]) is None:
        raise SessionError(f"{command[0]} is not on PATH; install it or add it to PATH")
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


async def _wait_for_public_dns(hostname: str) -> bool | None:
    """Wait until the hostname has an A record, without using the local resolver.

    A brand-new quick tunnel hostname is missing from DNS for a few seconds.
    Asking the local resolver during that window caches the failure for about
    a minute, and that negative entry then blocks this health check and Roblox
    Studio alike. Cloudflare's resolver is asked over HTTPS instead, which
    leaves the local cache clean so Studio resolves as soon as the record
    exists.

    Returns True once the record exists, False if it never showed up in time,
    and None when the public resolver could not be reached.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + DNS_SECONDS
    async with ClientSession(timeout=ClientTimeout(total=3)) as client:
        while loop.time() < deadline:
            try:
                async with client.get(
                    DOH_URL,
                    params={"name": hostname, "type": "A"},
                    headers={"accept": "application/dns-json"},
                ) as response:
                    if response.status == 200:
                        answer = await response.json(content_type=None)
                        if answer.get("Answer"):
                            return True
            except (OSError, TimeoutError, ValueError):
                return None
            await asyncio.sleep(0.5)
    return False


async def _wait_for_rojo(url: str, rojo: asyncio.subprocess.Process) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + READY_SECONDS
    next_report = PROGRESS_SECONDS
    last_error = "no response yet"
    async with ClientSession(timeout=ClientTimeout(total=5)) as client:
        while loop.time() < deadline:
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
                    last_error = f"Rojo answered HTTP {response.status}"
            except (OSError, TimeoutError) as error:
                last_error = str(error) or type(error).__name__
            waited = READY_SECONDS - (deadline - loop.time())
            if waited >= next_report:
                print(
                    f"Still waiting for the tunnel ({waited:.0f}s): {last_error}",
                    flush=True,
                )
                next_report += PROGRESS_SECONDS
            await asyncio.sleep(0.5)
    raise SessionError(
        f"the tunnel did not reach Rojo within {READY_SECONDS}s: {last_error}"
    )


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
            raise SessionError(
                f"cloudflared did not report a URL within {STARTUP_SECONDS}s"
            ) from error

        print(f"Tunnel URL: {url}", flush=True)
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
        published = await _wait_for_public_dns(hostname)
        if published is False:
            print(
                f"The hostname was not in DNS after {DNS_SECONDS}s; checking anyway",
                flush=True,
            )
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
