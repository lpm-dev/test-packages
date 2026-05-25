Direct `lpm ports` smoke fixture.

- `run_smokes.py install-ports` drives `lpm ports` / `lpm ports list`, `kill`, and `reset` against an isolated `LPM_HOME` plus a temporary listener process bound to a real local port.
- The smoke pins the documented split between declared service ports and persisted per-project overrides: `list` reports `lpm.json > services.<name>.port` entries, while `reset` only clears this project's `ports.toml` override entry.
- Assertions cover default human output, `--json` envelopes for `list`, live owner termination via `kill <port>`, the stable `already_free` envelope, and preservation of unrelated `ports.toml` entries during `reset`.
