import asyncio
import sys

import pytest

from rojo_share import session


@pytest.mark.asyncio
async def test_duration_stops_both_children(monkeypatch, tmp_path):
    project = tmp_path / "default.project.json"
    project.write_text("{}")
    children = []

    async def start_process(*command, cwd):
        output = (
            "print('https://example.trycloudflare.com', flush=True); "
            "import time; time.sleep(60)"
            if command[0] == "cloudflared"
            else "import time; time.sleep(60)"
        )
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            output,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        children.append(child)
        return child

    async def healthy(url, rojo):
        assert url == "https://example.trycloudflare.com"

    async def published(hostname):
        assert hostname == "example.trycloudflare.com"
        return True

    monkeypatch.setattr(session, "_start_process", start_process)
    monkeypatch.setattr(session, "_wait_for_public_dns", published)
    monkeypatch.setattr(session, "_wait_for_rojo", healthy)
    await session.serve(project, 34872, 0.05, 30)
    assert len(children) == 2
    assert all(child.returncode is not None for child in children)


@pytest.mark.asyncio
async def test_missing_binary_names_the_path_requirement(monkeypatch, tmp_path):
    monkeypatch.setattr(session.shutil, "which", lambda name: None)

    with pytest.raises(session.SessionError, match="cloudflared is not on PATH"):
        await session._start_process("cloudflared", "tunnel", cwd=tmp_path)


@pytest.mark.asyncio
async def test_unreachable_tunnel_reports_the_timeout(monkeypatch):
    monkeypatch.setattr(session, "READY_SECONDS", 0)

    with pytest.raises(session.SessionError, match="did not reach Rojo within 0s"):
        await session._wait_for_rojo("https://example.trycloudflare.com", object())


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    async def json(self, content_type=None):
        return self.payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    def get(self, url, **kwargs):
        if self.error is not None:
            raise self.error
        assert kwargs["params"]["type"] == "A"
        return FakeResponse(self.payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_public_dns_returns_once_the_record_exists(monkeypatch):
    payload = {"Answer": [{"type": 1, "data": "104.16.231.132"}]}
    monkeypatch.setattr(session, "ClientSession", lambda **kwargs: FakeSession(payload))

    assert await session._wait_for_public_dns("example.trycloudflare.com") is True


@pytest.mark.asyncio
async def test_public_dns_falls_back_when_the_resolver_is_unreachable(monkeypatch):
    session_stub = FakeSession(error=OSError("no route to host"))
    monkeypatch.setattr(session, "ClientSession", lambda **kwargs: session_stub)

    assert await session._wait_for_public_dns("example.trycloudflare.com") is None


@pytest.mark.asyncio
async def test_public_dns_gives_up_after_its_budget(monkeypatch):
    monkeypatch.setattr(session, "DNS_SECONDS", 0)

    assert await session._wait_for_public_dns("example.trycloudflare.com") is False
