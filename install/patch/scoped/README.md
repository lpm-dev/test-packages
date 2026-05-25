# install/patch/scoped

Local scoped-package `lpm patch` and `lpm patch-commit` command smoke fixture.

The runner installs one scoped dependency from the mock registry, authors a real patch through the public two-step CLI flow, and verifies the docs contract for scoped patch filenames.

Current checks:

- `lpm patch @smoke/patch-lib@1.0.0 --json` extracts a staging directory for the scoped package.
- `lpm patch-commit <staging_dir> --json` writes `patches/@smoke__patch-lib@1.0.0.patch` instead of a raw slash path.
- `package.json > lpm > patchedDependencies` keeps the manifest key as `@smoke/patch-lib@1.0.0` while the `path` field points at the sanitized on-disk filename.
- the next `lpm install` auto-applies the scoped patch through that sanitized path.

Relevant runner entry:

- `python3 run_smokes.py install-patch-scoped`
