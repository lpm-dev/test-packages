# install/migrate/yarn/basic

Local smoke fixture for `lpm migrate` from Yarn v1.

Checks:

- `lpm migrate --no-install --force --no-npmrc` detects `yarn.lock` and emits `lpm.lock` + `lpm.lockb`.
- The original `yarn.lock` stays untouched and is backed up before migration writes the LPM lockfile pair.
- Mixed `dependencies` and `devDependencies` are preserved in the converted LPM lockfile, with no install side effects.
