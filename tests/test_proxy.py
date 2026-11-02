import asyncio

import aiohttp
import pytest
from aiohttp import web

from rojo_share.proxy import create_app


async def start_server(app):
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, runner.addresses[0][1]


@pytest.mark.asyncio
async def test_http_proxy_and_local_open_guard():
    async def echo(request):
        return web.Response(
            status=201,
            body=await request.read(),
            headers={"X-Rojo-Test": request.headers["Host"]},
        )

    origin = web.Application()
    origin.router.add_route("*", "/{path:.*}", echo)
    origin_runner, origin_port = await start_server(origin)
    proxy_runner, proxy_port = await start_server(create_app(origin_port, 0.1))
    try:
        async with aiohttp.ClientSession() as client:
            async with client.get(
                f"http://127.0.0.1:{proxy_port}/api/rojo"
            ) as response:
                assert response.status == 201
                assert await response.read() == b""
            async with client.post(
                f"http://127.0.0.1:{proxy_port}/api/write?cursor=4",
                data=b"\x00\xff",
                headers={"Host": "example.trycloudflare.com"},
            ) as response:
                assert response.status == 201
                assert await response.read() == b"\x00\xff"
                assert response.headers["X-Rojo-Test"] == "example.trycloudflare.com"
            async with client.post(
                f"http://127.0.0.1:{proxy_port}/api/open/123"
            ) as response:
                assert response.status == 403
    finally:
        await proxy_runner.cleanup()
        await origin_runner.cleanup()


@pytest.mark.asyncio
async def test_websocket_forwards_binary_and_sends_ping():
    async def socket(request):
        assert request.headers["Host"] == "example.trycloudflare.com"
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for message in ws:
            if message.type == aiohttp.WSMsgType.BINARY:
                await ws.send_bytes(message.data[::-1])
        return ws

    origin = web.Application()
    origin.router.add_get("/api/socket/{cursor}", socket)
    origin_runner, origin_port = await start_server(origin)
    proxy_runner, proxy_port = await start_server(create_app(origin_port, 0.05))
    try:
        async with aiohttp.ClientSession() as client:
            async with client.ws_connect(
                f"http://127.0.0.1:{proxy_port}/api/socket/0",
                headers={"Host": "example.trycloudflare.com"},
                autoping=False,
            ) as ws:
                await ws.send_bytes(b"\x01\x02\x03")
                reply = await asyncio.wait_for(ws.receive(), 2)
                assert reply.data == b"\x03\x02\x01"
                ping = await asyncio.wait_for(ws.receive(), 2)
                assert ping.type == aiohttp.WSMsgType.PING
                await ws.pong(ping.data)
    finally:
        await proxy_runner.cleanup()
        await origin_runner.cleanup()
