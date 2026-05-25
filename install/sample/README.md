# install/sample

Seeded from `/Users/tolga/Desktop/sample` after the nested-package phantom-dependency investigation.

Included:

- root `package.json`
- nested `hey/` package with source-delivered files from `lpm add`
- project dotfiles useful for smoke repros

Excluded on copy:

- `node_modules/`
- `.lpm/`
- `lpm.lock`
- `lpm.lockb`
- `.DS_Store`

Use this fixture for live checks around `lpm install`, `lpm add`, alias handling, nested package boundaries, and other install-surface regressions.
