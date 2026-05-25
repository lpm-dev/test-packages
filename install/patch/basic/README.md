# install/patch/basic

Local `lpm patch` and `lpm patch-commit` command smoke fixture.

The runner installs one plain dependency from the mock registry, authors a real patch through the public two-step CLI flow, and then proves the generated patch applies on the next install.

Current checks:

- `lpm patch smoke-patch-lib --json` resolves the bare-name selector through the lockfile and writes a staging breadcrumb.
- the staging directory contains pristine upstream bytes rather than a previously patched project copy.
- `lpm patch-commit <staging_dir> --json` writes `patches/smoke-patch-lib@1.0.0.patch` and registers `lpm.patchedDependencies` in `package.json`.
- the next `lpm install` auto-applies the generated patch to the installed dependency.
- a fresh `lpm patch` after that reinstall still stages pristine upstream bytes, and `lpm patch-commit` aborts with `no changes detected` when nothing was edited.

Relevant runner entry:

- `python3 run_smokes.py install-patch`
