# workspace smoke fixtures

Use this directory for multi-package live/smoke scenarios:

- workspace install/update flows
- workspace member discovery
- workspace-specific lockfile behavior
- cross-member aliasing or boundary regressions

Current seed fixture:

- `basic/` — minimal workspace with one app, one local package, and one external registry dependency
- `complex/` — larger workspace with two apps, shared packages, and a transitive `workspace:*` chain
- `nested-boundary/` — workspace focused on nested `package.json` boundaries inside an app tree
- `targeting/` — workspace fixture for filtered installs, prod-only filter closure, git-ref test-pattern partitioning, combined name+path selectors, recursive run control flags, multi-member manifest edits, and no-match failures
- `pack/` — workspace fixture for `lpm pack --all`, root-level tsdown bin reuse, workspace JSON envelopes, and multi-member watch rejection
