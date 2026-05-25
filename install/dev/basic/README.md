# install/dev/basic

Direct smoke fixture for `python3 run_smokes.py install-dev`.

The scenario covers the current local `lpm dev` single-service contract:

- `.env.example` is copied to `.env` on first run when `.env` is absent
- `envSchema` enforcement blocks the run until `--no-env-check` is passed
- explicit `--env staging` layers `.env`, `.env.local`, `.env.staging`, and `.env.staging.local`
- args after `--` are forwarded verbatim to the `dev` script
- `--no-install` skips auto-install and surfaces the skip in the startup banner
- `--https` fails cleanly in non-interactive mode without `--yes`, then succeeds hermetically with a test trust store when `--yes` is supplied
- `--allow-ca-bootstrap` serves the generated root CA over `http://127.0.0.1:<port+1>` while the HTTPS dev run is active
- `--tunnel --inspect-port <N>` starts the browser inspector on exactly `N` once a refresh-backed session is seeded
- a successful loopback tunnel `hello` updates the `Tunnel:` banner, boots the inspector UI, and persists the session metadata in `.lpm/inspector.db`
- `--tunnel-auth` sends a per-session `X-Tunnel-Auth` header to the relay and prints the matching browser/header hints after connect
- `--tunnel --no-inspect` suppresses that inspector entirely even when an `--inspect-port` is also passed
- `--tunnel --inspect-port <occupied>` fails early with the strict address-in-use diagnostic before the dev script starts
