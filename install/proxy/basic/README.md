Direct `lpm proxy` smoke fixture.

- `run_smokes.py install-proxy` drives absent `status` / `list` / `stop` JSON contracts, detached daemon start-stop flow, service-install dry runs, privileged-port forwarder planning, config-backed listener defaults from `lpm.json`, and live `proxy.host` routing through a detached daemon plus `lpm dev`.
- The fixture keeps a single-service `proxy.host` baseline so the smoke can prove the documented top-level local-domain path without depending on the multi-service `install/dev` fixture.
- Assertions cover clean stdout/stderr separation for JSON mode, the no-daemon human status contract, dry-run argument planning, `lpm.json > proxy.port` default listener startup, live HTTP and HTTPS requests through the detached daemon, and HTTP-to-HTTPS redirect behavior.
