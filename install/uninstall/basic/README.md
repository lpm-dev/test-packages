# install/uninstall/basic

Local uninstall smoke fixture.

The runner seeds `node_modules/`, `lpm.lock`, and `lpm.lockb` at runtime, then verifies that:

- `lpm un` removes only the requested `dependencies` and `devDependencies`
- `peerDependencies`, `optionalDependencies`, and `lpm.trustedDependencies` stay untouched
- the lockfile pair and targeted `node_modules` entries are deleted

Relevant runner entry:

- `python3 run_smokes.py install-uninstall`
