"""Forward Rojo traffic while keeping each Studio WebSocket active."""

import asyncio
from contextlib import suppress

from aiohttp import (
    ClientError,
    ClientSession,
    ClientTimeout,
    ClientWebSocketResponse,
    WSMsgType,
    web,
)
from multidict import CIMultiDictProxy

MAX_WS_MESSAGE_BYTES = 64 * 1024 * 1024
HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
SESSION = web.AppKey("upstream_session", ClientSession)


def forward_headers(headers: CIMultiDictProxy[str]) -> dict[str, str]:
    excluded = HOP_HEADERS.copy()
    for value in headers.getall("Connection", []):
        excluded.update(part.strip().lower() for part in value.split(","))
    return {key: value for key, value in headers.items() if key.lower() not in excluded}


async def _relay_messages(
    source: ClientWebSocketResponse | web.WebSocketResponse,
    target: ClientWebSocketResponse | web.WebSocketResponse,
) -> None:
    async for message in source:
        if message.type == WSMsgType.BINARY:
            await target.send_bytes(message.data)
        elif message.type == WSMsgType.TEXT:
            await target.send_str(message.data)
        elif message.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR):
            break


async def _send_heartbeats(socket: web.WebSocketResponse, interval: float) -> None:
    while not socket.closed:
        await asyncio.sleep(interval)
        if not socket.closed:
            await socket.ping()


def create_app(rojo_port: int, heartbeat: float) -> web.Application:
    app = web.Application()
    origin = f"http://127.0.0.1:{rojo_port}"

    async def session_context(app: web.Application):
        async with ClientSession(timeout=ClientTimeout(total=None)) as session:
            app[SESSION] = session
            yield

    async def websocket(request: web.Request) -> web.WebSocketResponse:
        upstream_url = f"{origin}{request.raw_path}"
        try:
            upstream = await app[SESSION].ws_connect(
                upstream_url,
                headers={"Host": request.headers["Host"]},
                origin=request.headers.get("Origin"),
                max_msg_size=MAX_WS_MESSAGE_BYTES,
            )
        except (ClientError, OSError, TimeoutError) as error:
            raise web.HTTPBadGateway(text="Rojo WebSocket unavailable") from error

        downstream = web.WebSocketResponse(max_msg_size=MAX_WS_MESSAGE_BYTES)
        await downstream.prepare(request)
        tasks = [
            asyncio.create_task(_relay_messages(downstream, upstream)),
            asyncio.create_task(_relay_messages(upstream, downstream)),
            asyncio.create_task(_send_heartbeats(downstream, heartbeat)),
        ]
        try:
            await asyncio.wait(tasks[:2], return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with suppress(asyncio.CancelledError):
                    await task
            await upstream.close()
            await downstream.close()
        return downstream

    async def http(request: web.Request) -> web.StreamResponse:
        if request.path == "/api/open" or request.path.startswith("/api/open/"):
            raise web.HTTPForbidden(
                text="Local editor access is unavailable through a share"
            )
        headers = forward_headers(request.headers)
        headers.pop("Content-Length", None)
        try:
            async with app[SESSION].request(
                request.method,
                f"{origin}{request.raw_path}",
                headers=headers,
                data=request.content.iter_chunked(64 * 1024),
                allow_redirects=False,
                auto_decompress=False,
            ) as upstream:
                response_headers = forward_headers(upstream.headers)
                response_headers.pop("Content-Length", None)
                response = web.StreamResponse(
                    status=upstream.status, headers=response_headers
                )
                await response.prepare(request)
                async for chunk in upstream.content.iter_chunked(64 * 1024):
                    await response.write(chunk)
                await response.write_eof()
                return response
        except (ClientError, OSError, TimeoutError) as error:
            raise web.HTTPBadGateway(text="Rojo unavailable") from error

    app.cleanup_ctx.append(session_context)
    app.router.add_get("/api/socket/{cursor}", websocket)
    app.router.add_route("*", "/{path:.*}", http)
    return app
