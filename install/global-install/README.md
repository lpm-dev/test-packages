# global-install smoke fixtures

Mock-registry fixtures for `lpm install -g` and `lpm global` subcommands.

Covered by `python3 ../../run_smokes.py install-global-install` and `python3 ../../run_smokes.py install-global-commands` from this directory, or the same scenario names from the `test-packages/` root.

Current checks:

- global installs do not mutate the local fixture `package.json`
- successful installs write `LPM_HOME/global/manifest.toml`
- successful installs expose a shim under `LPM_HOME/bin`
- colliding bins fail with `--replace-bin` and `--alias` remediation hints
- alias-based re-install keeps the original shim owner and exposes the new tool under the alias name
- `lpm global link` records a local checkout, exposes its bin, and `lpm global path <pkg>` resolves back to the checkout
- `lpm global list --verbose` reports install roots, on-disk size, and linked source paths for registry-backed and local-link globals
- `lpm global list --outdated` reports `Current`, `Wanted`, `Latest`, and `Bins` for registry-backed globals while skipping local links
- `lpm global unlink` removes local-link shims and manifest state, while registry-backed globals still require `lpm global remove`
