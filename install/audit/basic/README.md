# install/audit/basic

Local `lpm audit` command smoke fixture.

The runner installs two mock-registry packages into an LPM-managed project:

- `audit-eval-pkg` carries a real `eval(...)` call so the normal audit path reports a high-severity behavioral finding.
- `audit-clean-pkg` stays clean so the scan has a stable control package.

After install, the runner also seeds a local `node_modules/leaky-pkg` with a recognizable AWS access-key pattern so `lpm audit --secrets` exercises the hardcoded-secret scanner without depending on remote metadata.

Current checks:

- `lpm audit --json` stays successful by default even when only high-severity behavior is present.
- `lpm audit --fail-on=behavior --json` exits non-zero for the eval-backed package.
- `lpm audit --secrets --fail-on=secrets --json` exits non-zero and reports the local secret finding.

Relevant runner entry:

- `python3 run_smokes.py install-audit`
