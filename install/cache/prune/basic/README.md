Direct `lpm cache prune` smoke fixture.

- `run_smokes.py install-cache-prune` first proves the missing-registry dry-run contract on a fresh isolated `LPM_HOME`.
- It then seeds a synthetic v2 store with one reachable package, one recent orphan, and one old orphan, and drives `lpm cache prune --project . --max-age 30d` in dry-run and `--apply` modes.
- The same smoke then corrupts `known-projects.json` and proves `lpm cache prune --apply` degrades safely: no orphan deletion, the warning names the corrupt-registry cause, and the parser reason is surfaced verbatim.
- Assertions pin the docs-backed manual-repair and degraded-mode contracts: `--project` bypasses `known-projects.json`, recent entries survive the age filter, only the old orphan link/object pair is removed on apply, and corrupt-registry runs stay tombstone-only.
