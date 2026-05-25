# install/trust/basic

Local `lpm trust` command smoke fixture.

The runner installs one scripted package and one clean control dependency into an LPM-managed project. The scripted package is then approved so the project gains a real `trustedDependencies` entry and a post-install trust snapshot baseline.

Current checks:

- `lpm trust diff --assert-none` stays clean immediately after install.
- approving the scripted package makes `lpm trust diff --json` report one added binding.
- `lpm trust diff --assert-none` exits non-zero once the trust list drifts from the last install snapshot.
- `lpm trust prune --dry-run --json` reports the stale binding without mutating `package.json`.
- `lpm trust prune --yes --json` removes the stale trust entry and returns the project to a clean diff state.

Relevant runner entry:

- `python3 run_smokes.py install-trust`
