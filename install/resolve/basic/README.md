# install/resolve/basic

Local `lpm resolve` command smoke fixture.

The runner resolves one bare package and one scoped package against the mock registry and verifies the docs contract for read-only metadata-only resolution.

Current checks:

- `lpm resolve smoke-resolve-bare @smoke/resolve-lib@^2 --json` returns a multi-package JSON envelope.
- the bare package resolves to its latest version.
- the scoped spec keeps the leading scope and uses the last `@` as the version separator.
- the command performs metadata lookups only and never downloads tarballs.
- `package.json`, `node_modules`, lockfiles, and the global content-addressable store stay untouched.

Relevant runner entry:

- `python3 run_smokes.py install-resolve`
