Direct `lpm cert` smoke fixture.

- `run_smokes.py install-cert` drives `lpm cert status`, `trust`, `uninstall`, and `generate` against an isolated HOME plus the test-only trust-store backend.
- The smoke pins the documented split between `generate` and `trust`: `generate` can mint the CA and project leaf, but trust-store installation still requires an explicit `lpm cert trust`.
- Assertions cover absent-state status JSON, isolated trust-store install/uninstall side effects, `generate --host` SAN refreshes, `cert.extraPermittedDns` forcing a leaf-plus-constrained-intermediate chain, audit-log actions, and the human-readable `Root CA` / `Project cert` status blocks.
