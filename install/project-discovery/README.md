# install/project-discovery

Fixtures for the `lpm install` project-root discovery contract from the docs.

Included:

- `nearest-ancestor/` — only the fixture root has a `package.json`; running from a nested subdirectory must mutate the root manifest and root install state.
- `fresh-dir/empty/` — no `package.json` anywhere under the fixture; `lpm install <pkg>` should auto-create a minimal manifest in the current directory.

Useful smoke checks:

- nearest-ancestor `package.json` discovery
- root-side lockfile and `node_modules` placement
- fresh-directory auto-manifest creation for `lpm install <pkg>`
