# install/migrate/bun/basic

Local smoke fixture for `lpm migrate` from Bun.

Checks:

- `lpm migrate --no-install --force --no-npmrc` detects `bun.lock` and emits `lpm.lock` + `lpm.lockb`.
- The original `bun.lock` stays untouched and is backed up before migration writes the LPM lockfile pair.
- No install side effects are allowed: no `node_modules`, no store population, and no `.npmrc` when `--no-npmrc` is set.
