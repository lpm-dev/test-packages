# install/upgrade/basic

Local `lpm upgrade` smoke fixture.

The runner seeds a public-npm `lpm.lock` entry for `smoke-upgrade-lib`, then verifies that:

- `lpm upgrade -y --dry-run --json` surfaces the npm package as a candidate
- `lpm upgrade -y` rewrites `package.json`, refreshes the lockfile pair, and installs the upgraded version

Relevant runner entry:

- `python3 run_smokes.py install-upgrade`
