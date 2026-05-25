Direct `lpm health` smoke fixture.

- `run_smokes.py install-health` drives `lpm health --json` against a mock registry and an unreachable registry URL.
- The smoke pins the successful JSON envelope (`success`, `healthy`, `registry_url`, `response_time_ms`), the single `/api/registry/health` round trip, and the non-zero exit contract when the registry is unreachable.
