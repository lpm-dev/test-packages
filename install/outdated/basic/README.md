# install/outdated/basic

Local `lpm outdated` smoke fixture.

The runner seeds a public-npm `lpm.lock` with one runtime dependency and one
dev dependency, then verifies that:

- `lpm outdated --json` reports both `dependencies` and `devDependencies`
- `wanted` is the highest version satisfying the declared range, while `latest`
  still shows the newest published version
- the text table renders the new `Section` and `Wanted` columns
- npm packages installed through the configured registry are still eligible for both `lpm outdated` and `lpm upgrade`
- a private-source npm-style package is skipped by both `lpm outdated` and
  `lpm upgrade --dry-run` without leaking its name to the configured registry

Relevant runner entry:

- `python3 run_smokes.py install-outdated`
- `python3 run_smokes.py install-outdated-skipped-private`
- `python3 run_smokes.py install-outdated-upgrade-configured-registry`
