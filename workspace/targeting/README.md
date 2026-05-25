# workspace/targeting

Workspace fixture for filtered installs and workspace-root targeting behavior.

Included:

- root workspace manifest with `apps/*` and `packages/*`
- two app members (`@smoke/target-web`, `@smoke/target-docs`) that should be matched by `--filter './apps/*'`
- one package member (`@smoke/target-core`) that should stay untouched by the app-only filter

Useful smoke checks:

- multi-member manifest edits through `--filter`
- root lockfile placement for filtered installs
- `--fail-if-no-match` returning non-zero on an empty filter expression
