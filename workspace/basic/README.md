# workspace/basic

Minimal workspace smoke fixture for `lpm` workspace flows.

Included:

- root workspace manifest with `apps/*` and `packages/*`
- `@smoke/core` workspace package
- `@smoke/app` workspace app depending on `@smoke/core` and one registry dep (`kleur`)

Useful smoke checks:

- workspace member discovery
- mixed workspace + registry installs
- root install writing one lockfile for the workspace
- local member linking from `@smoke/app` to `@smoke/core`
