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

    monkeypatch.setattr(session, "_start_process", start_process)
    monkeypatch.setattr(session, "_wait_for_rojo", healthy)
    await session.serve(project, 34872, 0.05, 30)
    assert len(children) == 2
    assert all(child.returncode is not None for child in children)
