# install/engines

Fixtures for install-time engine enforcement.

Included:

- `strict-fail/` — `engines.lpm` intentionally excludes the current CLI version; installs should fail before any manifest or lockfile mutation.
- `config-optout/` — same engine mismatch, but `package.json > lpm.engineStrict = false` allows the install to continue with warnings.

Useful smoke checks:

- hard failure on `engines.lpm` mismatch
- no side effects on an engine-gate failure path
- per-project `engineStrict = false` opt-out behavior
