# install/migrate/pnpm-patches/basic

Local smoke fixture for `lpm migrate` from pnpm with `patchedDependencies`.

Checks:

- `lpm migrate --no-install --force --no-npmrc` detects `pnpm-lock.yaml` and emits the LPM lockfile pair without install side effects.
- `pnpm.patchedDependencies` entries are translated into `package.json > lpm.patchedDependencies` with `originalIntegrity` bound from the migrated lockfile.
- The original `pnpm.patchedDependencies` block stays in place, and the canonical self-copy patch file stays byte-identical.
