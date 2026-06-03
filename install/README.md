# install smoke fixtures

Use this directory for single-project live/smoke scenarios:

- `lpm install`
- `lpm add`
- `lpm uninstall`
- alias handling
- nested-package boundaries
- lockfile and cache behavior in non-workspace projects

Current seed fixture:

- `sample/` — copied from `/Users/tolga/Desktop/sample` with generated state removed
- `source-delivery/` — clean consumer project for simple-path `lpm add`, bare-import surfacing, repeat-download and conflict-prompt coverage, alias rewriting, and follow-up remove flows
- `config-aware/` — clean consumer project for interactive config-aware `lpm add` coverage
- `read-only-routing/` — mock-registry fixture for `.npmrc`-routed `lpm info`, `lpm resolve`, `lpm search`, and `lpm download` checks when only npm-style endpoints are available
- `pack/` — local fixture for `lpm pack`, covering missing-tsdown fail-fast plus project-local tsdown resolution and stdout passthrough
- `upgrade/` — mock-registry fixture for `lpm upgrade` against public-npm and configured-registry lockfile sources
- `audit/` — mock-registry fixture for `lpm audit` and `lpm audit fix`, covering behavior/secrets gates plus direct-dependency fix dry-runs, apply flows, and custom-registry skip safety
- `create-project-smoke/` — migrated legacy single-project fixture for bootstrap/create flows
- `e2e-sandbox/` — migrated legacy single-project fixture for env/sandbox end-to-end behavior
- `test-upstream-proxy/` — migrated legacy single-project fixture for mixed upstream dependency installs
- `uninstall/` — local uninstall fixture for dependency/devDependency removal, lockfile-pair cleanup, and untouched peer/optional/trusted dependency state
- `project-discovery/` — install-root discovery fixtures for nearest-ancestor and fresh-dir behavior
- `engines/` — install fixtures for `engines.lpm` enforcement and opt-out coverage
- `peer-deps/` — mock-registry fixtures for optional-peer suppression, strict missing-peer failures, structured `peer_issues`, and peer-conflict auto-isolation
- `catalog/` — mock-registry fixtures for catalog save policy, `--catalog` forcing, cleanup pruning, and `pnpm-workspace.yaml` catalog ingestion
- `save-policy/` — mock-registry fixtures for dependency save-spec behavior (`^`, exact, explicit ranges, `@latest`, prerelease dist-tags, wildcard, re-install)
- `script-policy/` — mock-registry fixtures for default deny plus triage green and amber lifecycle-script behavior through project `.npmrc` routing
- `offline-integrity/` — tarball-URL fixtures for `--strict-integrity`, warm-store `--offline --strict-integrity`, and cold-store offline failures
- `minimum-release-age/` — mock-registry fixtures for the recent-publish cooldown gate, `--allow-new`, `--min-release-age=0`, and explicit pinned-spec blocking
- `audit-after-install/` — mock-registry fixtures for default-off audit summaries, env/config/CLI precedence, JSON envelopes, and informational failure injection
- `global-install/` — mock-registry fixtures for `lpm install -g`, `lpm uninstall -g`, `lpm global link` / `unlink` / `path` / `list`, manifest/shim writes, collision hints, outdated reporting, and alias success paths
- `source-delivery/` also backs the manifest-backed `lpm remove` smoke for bare-package add/remove reversal through a custom `--path`

Registry-backed install smokes run under an isolated `LPM_HOME` so they are repeatable even when package names and versions are reused across runs.

Relevant runner entries:

- `python3 run_smokes.py install-simple-source-delivery`
- `python3 run_smokes.py install-audit`
- `python3 run_smokes.py install-audit-fix`
- `python3 run_smokes.py install-dlx`
- `python3 run_smokes.py install-lpx`
- `python3 run_smokes.py install-remove`
- `python3 run_smokes.py install-read-only-routing`
- `python3 run_smokes.py install-pack`
- `python3 run_smokes.py install-upgrade`
- `python3 run_smokes.py install-outdated`
- `python3 run_smokes.py install-outdated-skipped-private`
- `python3 run_smokes.py install-outdated-upgrade-configured-registry`
- `python3 run_smokes.py install-uninstall`
- `python3 run_smokes.py install-uninstall-global`
- `python3 run_smokes.py install-global-install`
- `python3 run_smokes.py install-global-commands`
- `python3 run_smokes.py install-peer-deps`
- `python3 run_smokes.py install-catalog`
- `python3 run_smokes.py install-save-policy`
- `python3 run_smokes.py install-script-policy`
- `python3 run_smokes.py install-offline-integrity`
- `python3 run_smokes.py install-minimum-release-age`
- `python3 run_smokes.py install-audit-after-install`
- `python3 run_smokes.py workspace-uninstall`
