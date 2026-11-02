import argparse

import pytest

from rojo_share.cli import duration_seconds
from rojo_share.session import TUNNEL_URL


@pytest.mark.parametrize(
    ("value", "expected"), [("30s", 30), ("5m", 300), ("1h", 3600)]
)
def test_duration(value, expected):
    assert duration_seconds(value) == expected


@pytest.mark.parametrize("value", ["0s", "-1s", "2", "5minutes", "1.5h"])
def test_invalid_duration(value):
    with pytest.raises(argparse.ArgumentTypeError):
        duration_seconds(value)


def test_tunnel_url_from_cloudflared_log():
    log = "Your quick Tunnel has been created! Visit it at https://three-words.trycloudflare.com"
    assert TUNNEL_URL.search(log).group() == "https://three-words.trycloudflare.com"
