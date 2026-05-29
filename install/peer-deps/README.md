# peer-deps smoke fixtures

Mock-registry fixtures for documented peer-dependency install behavior.

Covered by `python3 ../../run_smokes.py install-peer-deps` from this directory, or `python3 run_smokes.py install-peer-deps` from the `test-packages/` root.

Current checks:

- optional peers stay absent and do not warn when the peer is missing
- `lpm.autoInstallPeers = false` surfaces missing required peers in `--json` as `peer_issues.missing`
- `--strict-peer-dependencies` fails the install on the same missing required peer
- cross-consumer peer conflicts emit structured `peer_issues`, keep `peer_conflicts` in sync, and persist `auto-isolated-peer-conflicts = true`
- explicit `--linker hoisted` opts out of peer-conflict auto-isolation
