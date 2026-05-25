# install/patch/binary

Local binary-edit rejection smoke fixture for `lpm patch` and `lpm patch-commit`.

The runner installs one dependency from the mock registry, extracts a staging directory, rewrites a text file with binary bytes, and verifies that `lpm patch-commit` rejects the edit without persisting any patch state.

Current checks:

- `lpm patch smoke-patch-binary-lib@1.0.0 --json` extracts a real staging directory for the installed package.
- replacing the staged text file with binary bytes makes `lpm patch-commit` fail with a `binary` error.
- the failed `patch-commit` writes no `patches/smoke-patch-binary-lib@1.0.0.patch` file.
- `package.json` stays unchanged after the rejected binary edit.

Relevant runner entry:

- `python3 run_smokes.py install-patch-binary`
