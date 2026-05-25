# install/tunnel/basic

Direct smoke fixture for `python3 run_smokes.py install-tunnel`.

The scenario seeds `.lpm/webhook-log.jsonl` and `.lpm/webhooks/*.json` directly,
then proves the current CLI split:

- relay-facing actions like `lpm tunnel claim` still require a refresh-backed `lpm login` session
- local `lpm tunnel inspect` works offline from the on-disk webhook log
- local `lpm tunnel log` filtering works from the same seeded data
- local `lpm tunnel replay` preserves the captured request body and signature headers
