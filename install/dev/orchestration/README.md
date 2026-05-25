# install/dev/orchestration

Direct orchestration fixture for `python3 run_smokes.py install-dev`.

The orchestration slice covers the current multi-service `lpm dev` contract:

- `dependsOn` starts services in dependency order and waits for each dependency to become ready
- readiness can be gated by either `readyPort` or `readyUrl`
- cross-service env injection provides `{SERVICE}_URL` and `{SERVICE}_PORT` to dependent services
- per-service `env` overrides are injected alongside the shared project env
- the orchestrator exits cleanly after the short-lived services finish
