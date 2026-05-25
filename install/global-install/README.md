# global-install smoke fixtures

Mock-registry fixtures for `lpm install -g`.

Covered by `python3 ../../run_smokes.py install-global-install` from this directory, or `python3 run_smokes.py install-global-install` from the `test-packages/` root.

Current checks:

- global installs do not mutate the local fixture `package.json`
- successful installs write `LPM_HOME/global/manifest.toml`
- successful installs expose a shim under `LPM_HOME/bin`
- colliding bins fail with `--replace-bin` and `--alias` remediation hints
- alias-based re-install keeps the original shim owner and exposes the new tool under the alias name
