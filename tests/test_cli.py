import pytest
import typer
from typer.testing import CliRunner

from rojo_share.cli import app, duration_seconds
from rojo_share.session import TUNNEL_URL

runner = CliRunner()


@pytest.mark.parametrize(
    ("value", "expected"), [("30s", 30), ("5m", 300), ("1h", 3600)]
)
def test_duration(value, expected):
    assert duration_seconds(value) == expected


@pytest.mark.parametrize("value", ["0s", "-1s", "2", "5minutes", "1.5h"])
def test_invalid_duration(value):
    with pytest.raises(typer.BadParameter):
        duration_seconds(value)


def test_serve_options(monkeypatch, tmp_path):
    project = tmp_path / "default.project.json"
    project.touch()
    calls = []

    async def fake_serve(*args):
        calls.append(args)

    monkeypatch.setattr("rojo_share.cli.serve", fake_serve)
    result = runner.invoke(
        app,
        [
            "serve",
            str(project),
            "--rojo-port",
            "1234",
            "--duration",
            "5m",
            "--heartbeat",
            "20s",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [(project.resolve(), 1234, 300, 20)]


@pytest.mark.parametrize("option", ["--duration", "--heartbeat"])
def test_invalid_duration_option(tmp_path, option):
    project = tmp_path / "default.project.json"
    project.touch()

    result = runner.invoke(app, ["serve", str(project), option, "0s"])

    assert result.exit_code == 2
    assert "use a positive duration" in result.output


def test_tunnel_url_from_cloudflared_log():
    log = "Your quick Tunnel has been created! Visit it at https://three-words.trycloudflare.com"
    assert TUNNEL_URL.search(log).group() == "https://three-words.trycloudflare.com"
