# install/approve-scripts/basic

Local `lpm approve-scripts` command smoke fixture.

The runner installs a mock-registry package with a real `postinstall` script under the default deny policy so the package enters the blocked set without executing its script.

Current checks:

- `lpm install` surfaces the `approve-scripts` guidance and writes `.lpm/build-state.json`.
- `lpm approve-scripts --list --json` reports the blocked package.
- `lpm approve-scripts <pkg> --dry-run --json` previews one approval without mutating `package.json`.
- `lpm approve-scripts <pkg> --json` writes the trusted dependency binding into `package.json`.
- A follow-up `lpm approve-scripts --list --json` shows the blocked set cleared.

Relevant runner entry:

- `python3 run_smokes.py install-approve-scripts`
