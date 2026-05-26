# install/pack

Single-project smoke fixture for `lpm pack`.

Useful smoke checks:

- fail-fast output when `tsdown` is missing from the local `node_modules/.bin` chain
- project-local `tsdown` resolution through `node_modules/.bin`
- forwarding of LPM-owned flags like `--config`, `--tsconfig`, `--target`, `--entry`, `--out-dir`, `--format`, `--platform`, `--dts`, `--minify`, and `--sourcemap`
- single-package stdout passthrough from the underlying backend

Relevant runner entry:

- `python3 run_smokes.py install-pack`
