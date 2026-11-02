# Rojo Share

Rojo Share runs a Rojo development server behind a temporary Cloudflare Quick Tunnel. It keeps idle Studio WebSocket connections active by sending protocol ping frames through a small local proxy. One `rojo-share serve` process owns one Rojo server, proxy, and tunnel; multiple processes can serve different projects concurrently.

The CLI is written in Python so its behavior is easy to inspect. Releases provide a Linux executable for Rokit, while source and tests remain in this repository. The tool does not require Cloudflare account credentials. A Quick Tunnel URL lasts only for its running process and changes when a session restarts.

The public URL exposes Rojo's development API while the session runs. The proxy denies `/api/open`, which would otherwise appear local to Rojo and could open a file in the container's editor. This does not authenticate the remaining API. Share URLs only with collaborators and stop sessions when finished.

Initial scope: Linux, Rojo 7.7.x, Cloudflare Quick Tunnels, one project per command. A Studio idle test is required before claiming the heartbeat works with the Roblox plugin.
