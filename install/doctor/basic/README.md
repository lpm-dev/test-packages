Direct `lpm doctor` smoke fixture.

- `run_smokes.py install-doctor` drives `lpm doctor`, `lpm doctor --all`, `lpm doctor list`, and fast `lpm doctor --fix` against an isolated `LPM_HOME` plus a mock registry.
- The smoke pins the fast-vs-all contract: the default preset must stay local-only, while `--all` performs the documented registry health probe and surfaces the extended inventory rows.
- The fix branch seeds `lpm.lock` without `lpm.lockb` and asserts fast `--fix` regenerates the binary lockfile while `fixes_applied` stays scoped to the fast-mode remediation set.
