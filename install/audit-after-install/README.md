# audit-after-install smoke fixtures

Fixture group for the install-time audit advisory:

- default off
- CLI flag, env var, and config-file enablement
- `--no-audit-after-install` precedence over env
- JSON `audit_summary` attachment with human line suppressed
- audit-hook failure stays informational and does not fail the install

Runner entry:

- `python3 run_smokes.py install-audit-after-install`
