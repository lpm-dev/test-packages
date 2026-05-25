# install/source-delivery

Single-project smoke fixture for source-delivery flows.

This project is intentionally light:

- root `package.json` exists so `lpm add` can record injected deps
- `tsconfig.json` declares the common `@/*` alias
- `components/` is the expected default landing area for source-delivered files

Useful smoke checks:

- `lpm add` into a clean project
- alias detection and import rewriting
- dependency injection into `package.json`
- follow-up remove/uninstall flows after a source add

Relevant runner entry:

- `python3 run_smokes.py install-remove` — bare-package source add into `custom/widgets`, then manifest-backed `lpm remove` cleanup
