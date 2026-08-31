# install/patch/scoped

Local scoped-package `lpm patch` and `lpm patch-commit` command smoke fixture.

The runner installs one scoped dependency from the mock registry, authors a real patch through the public two-step CLI flow, and verifies the docs contract for scoped patch filenames.

Current checks:

- `lpm patch @smoke/patch-lib@1.0.0 --json` extracts a staging directory for the scoped package.
- `lpm patch-commit <staging_dir> --json` writes a collision-resistant `patches/@smoke+patch-lib@1.0.0-<sha256>.patch` path instead of a raw slash path or the legacy `__` filename.
- `package.json > lpm > patchedDependencies` keeps the manifest key as `@smoke/patch-lib@1.0.0` while the `path` field matches the generated on-disk filename.
- the next `lpm install` auto-applies the scoped patch through that generated path.

Relevant runner entry:

- `python3 run_smokes.py install-patch-scoped`
