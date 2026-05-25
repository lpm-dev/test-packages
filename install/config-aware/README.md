# install/config-aware

Single-project smoke fixture for config-aware `lpm add` flows.

This project is intentionally clean so the interactive add can run without
conflict prompts:

- root `package.json` exists so injected dependencies have somewhere to land
- `tsconfig.json` declares the common `@/*` alias
- generated `components/`, `styles/`, and `lib/` output is reset by `run_smokes.py`

Useful smoke checks:

- interactive `configSchema` prompts
- alias-aware source delivery into `components/`
- config-driven file selection
- dependency injection for config-aware packages
