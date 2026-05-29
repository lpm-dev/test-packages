# catalog smoke fixtures

Mock-registry fixtures for documented catalog save-policy and cleanup behavior.

Covered by `python3 ../../run_smokes.py install-catalog` from this directory, or `python3 run_smokes.py install-catalog` from the `test-packages/` root.

Current checks:

- default/manual catalog mode keeps the raw save range even when the default catalog matches
- `--catalog` forces `catalog:` and `--catalog=<name>` forces `catalog:<name>`
- `catalogMode = "prefer"` saves `catalog:` on a matching default catalog entry
- `catalogMode = "strict"` fails before mutating `package.json` when the requested spec mismatches the catalog
- `cleanupUnusedCatalogs = true` prunes unused root catalog entries from `package.json`
- `pnpm-workspace.yaml` default catalogs resolve `catalog:` dependencies and prune unused entries when `cleanupUnusedCatalogs: true`
