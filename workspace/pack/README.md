# workspace/pack

Workspace smoke fixture for `lpm pack`.

Useful smoke checks:

- `lpm pack --all --json` member fan-out with one root-level `tsdown` binary reused from member directories
- per-member JSON envelope behavior for successful workspace runs
- `--fail-if-no-match` failures on empty workspace selections
- multi-member `--watch` rejection before any member backend process starts

Relevant runner entry:

- `python3 run_smokes.py workspace-pack`