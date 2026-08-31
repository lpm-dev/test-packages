# install/tunnel/basic

Direct smoke fixture for `python3 run_smokes.py install-tunnel`.

The scenario initializes `.lpm/inspector.db` through the CLI, seeds one capture
using the current SQLite schema, then proves the current CLI split:

- relay-facing actions like `lpm tunnel claim` still require a refresh-backed `lpm login` session
- local `lpm tunnel inspect` works offline from the inspector database
- local `lpm tunnel log` filtering works from the same seeded data
- local `lpm tunnel replay` preserves the captured request body and signature headers
