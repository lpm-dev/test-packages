# install/migrate/pnpm/basic

Local smoke fixture for `lpm migrate` from pnpm.

Checks:

- `lpm migrate --no-install --force --no-npmrc` detects `pnpm-lock.yaml` and emits the LPM lockfile pair without install side effects.
- `pnpm.overrides` entries are translated into `package.json > lpm.overrides`.
- The original `pnpm.overrides` block stays in place, and the pre-translation manifest is preserved in `package.json.backup`.
