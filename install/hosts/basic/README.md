Direct `lpm hosts` smoke fixture.

- `run_smokes.py install-hosts` drives `lpm hosts clean` against an isolated temporary hosts file instead of the real system file.
- The smoke pins both sides of the user-facing contract: `--json --yes` removes only LPM-managed blocks and writes a backup in `LPM_HOME`, while non-interactive `hosts clean` without `--yes` refuses before mutating anything.
