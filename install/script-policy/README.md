# script-policy smoke fixtures

Mock-registry fixtures for `lpm install` lifecycle-script behavior.

Covered by `python3 ../../run_smokes.py install-script-policy` from this directory, or `python3 run_smokes.py install-script-policy` from the `test-packages/` root.

Current checks:

- default deny blocks execution and surfaces the `approve-scripts` guidance
- triage green auto-build classifies the package as green and runs the script
- triage amber plus `--auto-build` still leaves the package blocked and reviewable

The runner uses an isolated `LPM_HOME` plus a per-project `.npmrc` pointing at the mock registry, so repeated runs stay hermetic without relying on proxy-mode routing.
