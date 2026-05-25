# offline-integrity smoke fixtures

Fixture group for the reproducible-install contract from `install.mdx`:

- tarball-URL deps without inline SRI must fail under `--strict-integrity`
- a warm store + lockfile must allow `lpm install --offline --strict-integrity`
- a cold store must fail helpfully under `--offline`

Runner entry:

- `python3 run_smokes.py install-offline-integrity`
