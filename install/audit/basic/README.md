# install/audit/basic

Local `lpm audit` / `lpm audit fix` command smoke fixture.

The runner installs two mock-registry packages into an LPM-managed project:

- `audit-eval-pkg` carries a real `eval(...)` call so the normal audit path reports a high-severity behavioral finding.
- `audit-clean-pkg` stays clean so the scan has a stable control package.

After install, the runner also seeds a local `node_modules/leaky-pkg` with a recognizable AWS access-key pattern so `lpm audit --secrets` exercises the hardcoded-secret scanner without depending on remote metadata.

Current checks:

- `lpm audit --json` stays successful by default even when only high-severity behavior is present.
- `lpm audit --fail-on=behavior --json` exits non-zero for the eval-backed package.
- `lpm audit --secrets --fail-on=secrets --json` exits non-zero and reports the local secret finding.
- `lpm audit --fix --dry-run --json` plans a vulnerable direct-dependency bump without mutating `package.json` or `node_modules`.
- `lpm audit fix --json` applies the same direct-dependency bump and refreshes `lpm.lock` plus `node_modules`.
- `lpm audit fix --dry-run --json` skips internal/custom-registry lockfile sources instead of disclosing package names to npm metadata endpoints.

Relevant runner entry:

- `python3 run_smokes.py install-audit`
- `python3 run_smokes.py install-audit-fix`
