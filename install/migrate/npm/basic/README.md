# install/migrate/npm/basic

Local smoke fixture for `lpm migrate` from npm.

Checks:

- `lpm migrate --dry-run` parses the npm lockfile, reports `source=npm`, and writes nothing.
- `lpm migrate --no-install --force` emits `lpm.lock` + `lpm.lockb`, creates the source-lockfile backup, and writes the default `@lpm.dev` scope to `.npmrc`.
- `lpm migrate --rollback` removes the generated LPM files and restores the project to the original npm-lockfile state.
