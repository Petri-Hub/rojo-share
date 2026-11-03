# rojo-share

`rojo-share` starts Rojo, a local WebSocket heartbeat proxy, and a Cloudflare Quick Tunnel as one temporary development session. It prints the HTTPS address to enter in the Rojo Studio plugin. No Cloudflare account is required.

```sh
rojo-share serve default.project.json --rojo-port 34872 --duration 1h --heartbeat 30s
```

Run the command from a project with its Rokit-pinned `rojo` on `PATH`. Install `cloudflared` on `PATH` too. Each simultaneous session needs a different `--rojo-port`. The proxy chooses its own local port. The Studio plugin uses the printed HTTPS host and port `443`.

A new tunnel hostname takes a few seconds to appear in DNS. The command checks the public record through Cloudflare's resolver over HTTPS first, so the local resolver does not cache a "not found" answer, then waits up to two minutes for the tunnel to reach Rojo and prints progress while waiting.

If `cloudflared` exits with `quick tunnel provisioning failed with status 429`, Cloudflare is rate limiting new tunnels for your network ([error 1015](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1015/)). The provisioning endpoint reports the wait in a `Retry-After` header, 40 minutes when it was last measured, but `cloudflared` discards it. Wait it out and avoid retrying: repeated attempts can extend the block. This is not the `429` in the Quick Tunnels documentation, which is returned to traffic on a tunnel that already has 200 requests in flight.

`--duration` is the maximum session lifetime; `--heartbeat` is the WebSocket ping period. Both accept positive whole numbers followed by `s`, `m`, or `h`. The defaults are `1h` and `30s`. Press Ctrl-C to stop all processes. A restarted Quick Tunnel gets a new URL.

The public URL exposes Rojo's development API while the command runs. `/api/open` is blocked because Rojo would mistake the local proxy for a local user. This does not authenticate the remaining API. Stop the session when the work is done.

Development:

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

See [PROJECT.md](PROJECT.md) for scope. Tagged releases build a Linux executable for Rokit. Publish the first tag after the Studio heartbeat test passes.
