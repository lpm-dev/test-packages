# install/source-delivery

Single-project smoke fixture for source-delivery flows.

This project is intentionally light:

- root `package.json` exists so `lpm add` can record injected deps
- `tsconfig.json` declares the common `@/*` alias
- `components/` is the expected default landing area for source-delivered files

Useful smoke checks:

- simple-path `lpm add` into a clean project
- bare-import surfacing for npm/private-registry source copies
- repeated `lpm add` re-downloads instead of reusing a persisted store tarball
- conflict warnings and default skip behavior for existing files
- alias detection and import rewriting
- dependency injection into `package.json`
- follow-up remove/uninstall flows after a source add

Relevant runner entry:

- `python3 run_smokes.py install-simple-source-delivery` — simple npm/private-registry source copy, bare-import notice, JSON `external_imports`, repeat-download contract, and conflict prompt coverage
- `python3 run_smokes.py install-remove` — bare-package source add into `custom/widgets`, then manifest-backed `lpm remove` cleanup
