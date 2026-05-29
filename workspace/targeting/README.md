# workspace/targeting

Workspace fixture for filtered installs, recursive workspace-filter controls, and workspace-root targeting behavior.

Included:

- root workspace manifest with `apps/*` and `packages/*`
- two app members (`@smoke/target-web`, `@smoke/target-docs`) that should be matched by `--filter './apps/*'`
- one package member (`@smoke/target-core`) that should stay untouched by the app-only filter
- dynamic smoke-only package seeds for `--filter-prod`, `--no-bail`, `--workspace-concurrency`, `--test-pattern`, `pkg{path}`, and git-ref ignore-pattern checks

Useful smoke checks:

- multi-member manifest edits through `--filter`
- recursive run controls through `--filter-prod`, `--no-bail`, and `--workspace-concurrency`
- git-ref selection with `--changed-files-ignore-pattern` and `--test-pattern`
- combined `pkg{path}` selectors intersecting package-name and directory matches
- root lockfile placement for filtered installs
- `--fail-if-no-match` returning non-zero on an empty filter expression
