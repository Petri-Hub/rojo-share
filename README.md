<h1 align="center">🌐 rojo-share</h1>

<br>

<h3 align="center">A Rojo session shared through a temporary Cloudflare tunnel.<br>One command starts Rojo, a heartbeat proxy and the tunnel, then prints the address for Studio.</h3>

<p align="center">
  <a href="https://github.com/Petri-Hub/rojo-share/releases"><img alt="Release" src="https://img.shields.io/github/v/release/Petri-Hub/rojo-share?logo=github&logoColor=white" /></a> <a href="https://github.com/Petri-Hub/rojo-share/actions/workflows/quality.yml"><img alt="Quality" src="https://github.com/Petri-Hub/rojo-share/actions/workflows/quality.yml/badge.svg?branch=main" /></a> <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white" /> <a href="LICENSE"><img alt="License" src="https://img.shields.io/github/license/Petri-Hub/rojo-share" /></a> <img alt="Time spent" src="https://img.shields.io/endpoint?url=https%3A%2F%2Flab-wakapi.petri.zip%2Fapi%2Fcompat%2Fshields%2Fv1%2FPetri%2Fproject%3Arojo-share%2Finterval%3Aall_time&label=time%20spent&logo=wakatime&logoColor=white&color=blue&cacheSeconds=3600" />
</p>

<br>

## About

> **TL;DR:** `rojo-share serve` starts Rojo, a small proxy that pings each Studio WebSocket so it does not go idle, and a Cloudflare Quick Tunnel as one session. It prints the `https://….trycloudflare.com` address to paste into the Rojo Studio plugin. No Cloudflare account is involved, and the URL lasts exactly as long as the command runs.

## Why it exists

[I am building a Roblox game with friends and an AI agent](https://github.com/Petri-Hub/roblox-with-swe). Rojo keeps the code in Git and syncs it into Roblox Studio over a WebSocket, which normally means everyone works on the same machine or the same network. A Quick Tunnel puts that Rojo server on a public HTTPS address without a Cloudflare account, a domain or a DNS record, so a collaborator can connect from anywhere.

The tunnel charges for that convenience: a Quick Tunnel drops a connection that stays quiet, and Studio then reports that the sync stopped. The answer is not a tunnel setting but traffic. The proxy sends a WebSocket ping every `--heartbeat` seconds, inside the connection the plugin already opened, so the session never counts as idle while nobody is editing.

## How it works

A session owns three processes, and the traffic always enters through the tunnel:

```text
Roblox Studio  ──HTTPS/WSS──▶  cloudflared  ──▶  proxy (local port)  ──▶  Rojo (127.0.0.1:34872)
     ▲                                                │
     └──────────────── ping every heartbeat ───────────┘
```

1. The proxy binds to an ephemeral local port. It forwards HTTP and WebSocket traffic to Rojo, and it refuses `/api/open`.
2. `cloudflared` opens a Quick Tunnel to that port and reports a fresh hostname. The command prints the URL as soon as it exists.
3. Rojo starts on `127.0.0.1:<rojo-port>` with `--allowed-hosts` set to that hostname, because Rojo rejects a public host it was never told about.
4. The command waits for the hostname to exist in public DNS and for `/api/rojo` to answer through the tunnel, then prints the Studio URL on port `443`.

Only then is the session reported as ready. From that point the command runs until `--duration` elapses or you press Ctrl-C, and it stops all three processes on the way out.

## Scope

Rojo Share targets one setup: Linux x86_64, Rojo 7.7.x, Cloudflare Quick Tunnels and one project per command. Several projects mean several `serve` processes with different `--rojo-port` values, each with its own tunnel and URL.

The heartbeat is the part still being proven with the real plugin. A session has to survive an idle period long enough to drop a bare tunnel, and that test needs Roblox Studio and a collaborator, so it stays open in the roadmap until it passes. Until then, the ping is the design rather than a guarantee.

## Philosophy

**One command, one session.**<br>
`serve` owns Rojo, the proxy and the tunnel together, so there is no second terminal to watch and no process left behind. Two sessions are two processes with different `--rojo-port` values.

**Show the address early.**<br>
The tunnel URL is printed the moment `cloudflared` reports it, before the tunnel is known to work. You can paste it into Studio while the health check finishes, and a failed start still leaves behind the address it was trying.

**Keep Studio connected without changing Studio.**<br>
The heartbeat rides inside the WebSocket the plugin already opened, so neither Rojo nor the plugin needs to know about it. A new setting would have been a new thing to configure on every collaborator's machine.

**Say why it failed.**<br>
A missing binary, a rejected tunnel, a hostname that is not in DNS yet and a Rojo that never answered all end in different sentences. The message names the cause instead of asking you to guess.

**Python, because it should be readable.**<br>
The CLI and the proxy are small enough to read in one sitting. The released executable is a build artifact, not a second implementation.

## Usage

```sh
rojo-share serve default.project.json
```

| Argument or option | Default | Description |
|---|---|---|
| `project` | — | The Rojo project **file**, such as `default.project.json` |
| `--rojo-port` | `34872` | Local port for the Rojo server; each concurrent session needs its own |
| `--duration` | `1h` | Maximum session lifetime |
| `--heartbeat` | `30s` | WebSocket ping period sent to Studio |

`--duration` and `--heartbeat` accept positive whole numbers followed by `s`, `m`, or `h`. Ctrl-C stops the session and its children.

## Notes

### A new hostname takes a moment to exist

Every session gets a new `trycloudflare.com` hostname, and it is missing from DNS for a few seconds after the tunnel starts. The command asks Cloudflare's resolver over HTTPS whether the record exists before touching the system resolver, because a first lookup during that window caches "not found" for about a minute and that negative entry then blocks the health check and Studio alike. If the record never appears, the session says so and keeps checking up to a time limit rather than failing silently.

### Cloudflare limits how many tunnels you create

`quick tunnel provisioning failed with status 429` comes from Cloudflare's own rate limit ([error 1015](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1015/)), not from this command. The provisioning endpoint states the wait in a `Retry-After` header, forty minutes when it was last measured, but `cloudflared` discards it. Wait it out and avoid retrying, since repeated attempts extend the block. This is a different `429` from the one in the Quick Tunnels documentation, which is returned to traffic on a tunnel that already has 200 requests in flight.

### The URL is public while the session runs

Anyone with the address reaches Rojo's development API for as long as the command runs. `/api/open` is denied because Rojo would mistake the local proxy for a local user and open a file in the editor. That denial is not authentication for the rest of the API. Share the URL with the people you are working with, and stop the session when you are done.

## Installation

Releases are Linux executables published as a zip, and [Rokit](https://github.com/rojo-rbx/rokit) installs them from the tag. Add the tool to a project's `rokit.toml`:

```toml
[tools]
rojo = "rojo-rbx/rojo@7.7.1"
rojo-share = "Petri-Hub/rojo-share@0.1.2"
```

Then install it, trusting the repository once so Rokit accepts a release it has not seen:

```sh
rokit trust Petri-Hub/rojo-share
rokit install
```

`cloudflared` is not managed by Rokit. Install it and keep it on `PATH`; the command checks for it, and for `rojo`, before starting anything.

## Technologies

| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; | Technology | Used for |
|:---:|---|---|
| <img src="https://raw.githubusercontent.com/rojo-rbx/rojo/master/assets/brand_images/logo-512.png" width="20" height="20" alt="" /> | [Rojo](https://rojo.space/docs/) | The development server that syncs the project into Studio over a WebSocket |
| <img src="https://cdn.simpleicons.org/cloudflare" width="20" height="20" alt="" /> | [Cloudflare Quick Tunnel](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels) | The public HTTPS address, opened by `cloudflared` without an account |
| <img src="https://cdn.simpleicons.org/python" width="20" height="20" alt="" /> | [Python](https://docs.python.org/3/) | The language of the command and the proxy |
| <img src="https://cdn.simpleicons.org/typer" width="20" height="20" alt="" /> | [Typer](https://typer.tiangolo.com/) | The command line, its arguments, help and exit codes |
| <img src="https://cdn.simpleicons.org/aiohttp" width="20" height="20" alt="" /> | [aiohttp](https://docs.aiohttp.org/) | The proxy, the WebSocket relay, the heartbeat and the health check |
| <img src="https://cdn.simpleicons.org/uv" width="20" height="20" alt="" /> | [uv](https://docs.astral.sh/uv/) | Dependencies, local runs and the locked build |
| <img src="https://cdn.simpleicons.org/githubactions" width="20" height="20" alt="" /> | [GitHub Actions](https://docs.github.com/actions) | Quality on every push, and the executable published on every tag |

## What's inside

```text
.
├── .github/
│   └── workflows/
│       ├── quality.yml        # lockfile, lint, format, tests and build on 3.11 and 3.12
│       └── release.yml        # one-file Linux executable, zipped with SHA256SUMS
│
├── src/rojo_share/
│   ├── cli.py                 # the command, its options and the exit codes
│   ├── proxy.py               # HTTP and WebSocket forwarding, heartbeat, /api/open denial
│   └── session.py             # the three processes, the DNS check and the health check
│
├── tests/                     # behavior checks for the command and the session
├── pyproject.toml             # package metadata and dependencies
└── uv.lock                    # the locked dependency set
```

## Development

### Requirements

- [Git](https://git-scm.com/install/) to work with the repository.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) to install Python and project dependencies.

### Setup

```bash
# Install the dependencies pinned in uv.lock.
uv sync --locked
```

### Checking

```bash
# Check Python code with Ruff.
uv run ruff check .

# Check Python formatting.
uv run ruff format --check .

# Run the tests.
uv run pytest
```

## Roadmap

### Done

- ✅ A Typer command that starts Rojo, the proxy and the tunnel as one session
- ✅ A proxy that forwards HTTP and WebSocket traffic and refuses `/api/open`
- ✅ A heartbeat that pings Studio inside the WebSocket it already opened
- ✅ A session lifetime and a heartbeat period, both with `s`, `m` and `h` units
- ✅ The tunnel URL printed as soon as `cloudflared` reports it
- ✅ A startup check for `cloudflared` and `rojo` on `PATH`
- ✅ A tunnel health check that waits for the hostname in public DNS before it checks through it
- ✅ Failure messages that name the last `cloudflared` line and the error 1015 rate limit
- ✅ Quality on Python 3.11 and 3.12, and a zipped Linux executable per tag
- ✅ Published through Rokit, pinned in a project's `rokit.toml`

### Open

- ⬜ Confirm that an idle Studio session survives past the point a bare tunnel drops it
- ⬜ Try a named tunnel as an option, for a URL that survives a restart
- ⬜ Widen the release beyond Linux x86_64

## Related projects

- [roblox-with-swe](https://github.com/Petri-Hub/roblox-with-swe) is the game this was written for, and where the Rokit pin lives.
- [pepper](https://github.com/Petri-Hub/pepper) documents the agents that share these sessions.
- [lab](https://github.com/Petri-Hub/lab) runs the sandbox where one of them works.
- [roblox-assets-mcp](https://github.com/Petri-Hub/roblox-assets-mcp) gives an assistant the Creator Store assets a game needs.

## Disclaimer

This project is unofficial. It is not made by, affiliated with or endorsed by Roblox Corporation or the Rojo project.

## License

This repository is licensed under the [MIT License](LICENSE).

## References

- [Rojo documentation](https://rojo.space/docs/): the project format, the server and the Studio plugin.
- [Rojo on GitHub](https://github.com/rojo-rbx/rojo): the server this command runs, from [rojo-rbx](https://github.com/rojo-rbx).
- [Rokit](https://github.com/rojo-rbx/rokit): the toolchain manager that installs the releases here.
- [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels): what a Quick Tunnel is, and its documented limits.
- [cloudflared downloads](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/): the binary this command expects on `PATH`.
- [Error 1015](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1015/): the rate limit behind a refused tunnel.
- [Typer](https://typer.tiangolo.com/): the command line library, with the argument and option types used here.
- [aiohttp](https://docs.aiohttp.org/): the HTTP client and server behind the proxy and the heartbeat.
