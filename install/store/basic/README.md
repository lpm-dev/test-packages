Direct `lpm store` smoke fixture.

- `run_smokes.py install-store` drives `lpm store path`, fast and deep `lpm store verify`, `lpm store verify --fix`, and `lpm store clean` against an isolated `LPM_HOME`.
- The smoke seeds both v1 and v2 store state, plus a local `lpm.lock`, so the direct checks pin the documented fast-vs-deep verify boundary, the security-cache refresh behavior behind `--fix`, and the full-store wipe semantics.
- Assertions also pin the post-clean control-file contract: `v1/` and `v2/` are gone, but the outer store root and `.gc.lock*` files remain.
