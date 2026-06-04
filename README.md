# test-packages

Local live/smoke fixtures for manual `lpm` testing.

## Runner

Use `python3 run_smokes.py --list` to see the available scenarios.

Use `python3 run_smokes.py all` to rebuild `lpm-rs`, reset the relevant fixtures,
and run the current live smoke suite end to end.

Use `LPM_SMOKE_NATIVE_SECURITY_UNLOCK=1 python3 run_smokes.py install-security`
to opt into the native macOS approval dialog path for `lpm security unlock`.
Without that env var, the security smoke only covers the automatable refusal and
status/config/proposal surfaces.

The runner is Python on purpose: it uses the standard-library PTY support to
drive real interactive `lpm add` prompts without adding project dependencies.

## Layout

- `install/` — single-project fixtures for `lpm install`, `lpm add`, `lpm uninstall`, and related flows.
- `workspace/` — multi-package fixtures for workspace commands and workspace-specific behaviors.

## Notes

- This folder is the unified home for local end-to-end and live smoke fixtures.
- `lpm-test-packages/` remains for package publishing inputs and source-package authoring fixtures, not consumer-side E2E runs.
- Fixtures here should stay scrubbed of generated state unless a specific smoke case needs committed lockfiles or caches.
- Registry-backed smoke scenarios use an isolated `LPM_HOME` per run so repeated runs do not reuse stale packument or tarball cache entries.

## Current Fixtures

- `install/sample` — nested-package install fixture copied from the desktop repro project
- `install/source-delivery` — clean consumer project for simple-path `lpm add`, bare-import surfacing, repeat-download and conflict-prompt coverage, manifest-backed `lpm remove`, and alias/dependency-injection checks
- `install/config-aware` — clean consumer project for interactive config-aware `lpm add` coverage
- `install/read-only-routing` — mock-registry fixture for `lpm info`, `lpm resolve`, `lpm search`, and `lpm download` through project-local `.npmrc` routing without the proxy metadata path
- `install/download` — mock-registry fixture for direct `lpm download` runs, covering canonical `--output` paths, stripped extraction layout, integrity verification, and no install side-effects
- `install/resolve` — mock-registry fixture for direct `lpm resolve` runs, covering multi-spec JSON output, scoped last-`@` parsing, metadata-only routing, and no-download read-only behavior
- `install/cache` — local fixture for direct `lpm cache path`, `lpm cache clean`, and `lpm cache clear` runs, covering JSON output, subcategory targeting, and the cache/store boundary
- `install/cache/prune` — local fixture for direct `lpm cache prune` runs, covering missing-registry and corrupt-registry degraded modes plus `--project`/`--max-age` orphan cleanup on a seeded v2 store
- `install/store` — local fixture for direct `lpm store` runs, covering path output, fast-vs-deep verify semantics, `--fix` security-cache refreshes, and blunt `clean` wipes across both v1 and v2 store state
- `install/graph` — local fixture for direct `lpm graph` runs, covering resolved tree output, substring `--filter` semantics, graph-level depth pruning across json/stats/html, and the `--no-open` warning contract
- `install/pack` — local fixture for direct `lpm pack` runs, covering missing-tsdown fail-fast behavior plus project-local tsdown resolution and direct single-package stdout passthrough
- `install/dev` — local fixture set for direct `lpm dev` runs, covering `.env.example` bootstrap, env-schema validation vs `--no-env-check`, explicit `--env` layering, forwarded args after `--`, the `--no-install` startup banner, hermetic `--https` consent/bootstrap behavior, successful loopback tunnel hello plus persisted inspector session state and `--tunnel-auth`, refresh-backed tunnel inspector/no-inspect/strict inspect-port behavior, and multi-service `dependsOn` orchestration with cross-service env injection
- `install/tunnel` — local fixture for direct `lpm tunnel` runs, covering auth-gated relay actions plus local `inspect`, `log`, and `replay` behavior from seeded on-disk webhook logs
- `install/ports` — local fixture for direct `lpm ports` runs, covering declared-port listing, missing-port kill failures, live owner termination, and per-project `ports.toml` reset semantics
- `install/cert` — local fixture for direct `lpm cert` runs, covering absent status, isolated trust-store install/uninstall, `generate --host` SAN refreshes, and the human-readable status blocks
- `install/doctor` — local + mock-registry fixture for direct `lpm doctor` runs, covering fast-vs-all preset split, live `doctor list` filters, and fast `--fix` regeneration of `lpm.lockb` without dispatching extended-only fixes
- `install/doctor-drift` — local + mock-registry fixture for `lpm doctor` deps-sync drift after a prior successful install, covering request-free fast detection, `--fix` install dispatch, and a clean rerun
- `install/lockfile-contract` — mock-registry fixture set for healthy lockfile fast-path reuse, missing `lpm.lockb` regeneration without extra registry traffic, and missing `lpm.lock` fallback to a fresh resolve path
- `install/adversarial-packument` — mock-registry fixture set for install fail-fast behavior on invalid packument JSON, missing dist tarball metadata, invalid `versions` shapes, and absent `versions` blocks without project writes
- `install/corrupt-tarball` — mock-registry fixture set for install failures on truncated gzip bodies, gzip-wrapped non-tar payloads, and integrity mismatches without lockfile or manifest mutation
- `install/rollback` — mock-registry fixture for transactional integrity-failure rollback and a clean rerun in the same fixture
- `install/permissions-collision` — local + mock-registry fixture for write-denied project roots and occupied `lpm.lock` path collisions, including recovery after removing the collision
- `install/health` — mock-registry fixture for direct `lpm health` runs, covering successful JSON output, the single `/api/registry/health` round trip, and unreachable-registry non-zero exits
- `install/migrate/npm` — local fixture for `lpm migrate` from npm, covering `--dry-run` no-write behavior, lockfile/`.npmrc` backup creation, and `--rollback` cleanup back to the original foreign-lockfile state
- `install/migrate/pnpm` — local fixture for `lpm migrate` from pnpm, covering `pnpm.overrides` translation into `lpm.overrides`, preserved `pnpm.overrides`, manifest backups, and `--no-install --no-npmrc` no-side-effect behavior
- `install/migrate/pnpm/patches` — local fixture for `lpm migrate` from pnpm, covering `pnpm.patchedDependencies` translation into `lpm.patchedDependencies`, `originalIntegrity` binding, canonical patch-path preservation, and intact patch bytes on the self-copy path
- `install/migrate/bun` — local fixture for `lpm migrate` from Bun, covering Bun lockfile detection, LPM lockfile-pair emission, source-lockfile preservation, and `--no-install --no-npmrc` no-side-effect behavior
- `install/migrate/yarn` — local fixture for `lpm migrate` from Yarn v1, covering Yarn lock detection, mixed dependency plus devDependency conversion, source-lockfile preservation, and `--no-install --no-npmrc` no-side-effect behavior
- `install/upgrade` — mock-registry fixture for `lpm upgrade` on public-npm and configured-registry lockfile sources, covering dry-run candidate discovery and real end-to-end upgrade application
- `install/outdated` — mock-registry fixture for `lpm outdated` across `dependencies` and `devDependencies`, including resolved `wanted` vs `latest` semantics, configured-registry npm inclusion, and the shared skipped-private no-leak path with `lpm upgrade --dry-run`
- `install/uninstall` — local uninstall fixture for dependency/devDependency removal, lockfile-pair cleanup, and untouched peer/optional/trusted dependency state
- `install/uninstall-bin-cleanup` — mock-registry fixture for scoped package uninstall cleanup, covering owned local `.bin` shim removal while preserving unrelated shims
- `install/create-project-smoke` — migrated single-project fixture for project bootstrap flows
- `install/e2e-sandbox` — migrated single-project fixture for env/sandbox-related end-to-end checks
- `install/test-upstream-proxy` — migrated single-project fixture for mixed upstream-registry dependency coverage
- `install/project-discovery` — new fixture set for nearest-ancestor root discovery and fresh-directory auto-manifest coverage
- `install/engines` — new fixture set for `engines.lpm` enforcement and opt-out behavior
- `install/peer-deps` — mock-registry fixture set for optional-peer suppression, strict missing-peer failures, structured `peer_issues`, and peer-conflict auto-isolation
- `install/catalog` — mock-registry fixture set for manual/prefer/strict catalog save policy, `--catalog` forcing, package.json cleanup pruning, and `pnpm-workspace.yaml` catalog ingestion
- `install/save-policy` — mock-registry fixture set for save-prefix, explicit range, latest-tag, prerelease, wildcard, and re-install coverage
- `install/optional-deps-hard-mode` — mock-registry fixture set for transitive optional dependency trust previews, platform-gated skips, missing optional fetch skips, and optional-plus-peer interactions, plus an explicit trust-unlock path for optional script execution
- `install/scoped-matrix` — mock-registry fixture set for scoped package bare installs, beta dist-tag resolution, local bin wiring, scoped uninstall manifest cleanup, and scoped upgrade application
- `install/output-contract` — mock-registry fixture set for human-vs-JSON stdout behavior, stable JSON failure envelopes, and approval-required output contracts
- `install/script-policy` — mock-registry fixture set for default deny, guarded `lpm.scriptPolicy = "allow"` and `"triage"` proposals, explicit `scripts-allow` unlock execution, lifecycle ordering, targeted rebuild, and the current auto-build failure surface
- `install/offline-integrity` — tarball-URL fixture set for `--strict-integrity`, warm-store offline relink, and cold offline failure coverage
- `install/minimum-release-age` — mock-registry fixture set for recent-publish cooldown defaults, guarded CLI/package weakeners, and explicit pinned-spec blocking
- `install/security` — local + mock-registry fixture set for `lpm security status`, guarded `lpm config` writes, guarded repo proposals, default-target `unlock` / `lock` coverage, signed audit-log coverage, and the optional native unlock + project lock success path
- `install/audit-after-install` — mock-registry fixture set for default-off audit summaries, precedence resolution, JSON envelopes, and informational audit-hook failures
- `install/audit` — mock-registry fixture for direct `lpm audit` and `lpm audit fix` runs, covering default informational high behaviors, `--fail-on=behavior`, `--secrets --fail-on=secrets`, canonical/alias fix flows, and custom-registry skip safety
- `install/query` — mock-registry fixture for direct `lpm query` runs, covering selector matches, `--assert-none`, `--count --json`, and Mermaid output
- `install/approve-scripts` — mock-registry fixture for direct `lpm approve-scripts` runs, covering blocked-set listing, dry-run named approval preview, and guarded named approval refusal
- `install/trust` — mock-registry fixture for direct `lpm trust` runs, covering guarded approval refusal plus diff/prune behavior over direct manifest-and-snapshot drift
- `install/rebuild` — mock-registry fixture for direct `lpm rebuild` runs, covering guarded trust approval refusal plus deny-mode skip messaging with no script execution
- `install/patch` — mock-registry fixture for direct `lpm patch` and `lpm patch-commit` runs, covering lockfile-based extraction, patch file generation, manifest registration, reinstall auto-apply, pristine re-extracts, and no-change aborts
- `install/patch/scoped` — mock-registry fixture for scoped `lpm patch` and `lpm patch-commit` runs, covering `/` to `__` filename sanitization, manifest key preservation, and reinstall auto-apply through the sanitized patch path
- `install/patch/binary` — mock-registry fixture for `lpm patch-commit` rejection of binary edits, covering the error path plus the absence of generated patch files or manifest mutation after the failed commit
- `install/global-install` — mock-registry fixture set for `install -g` manifest writes, `uninstall -g` cleanup, `lpm global` link/unlink/path/list coverage, shim creation, collision hints, outdated reporting, and alias-based collision resolution
- `workspace/basic` — minimal workspace fixture with one local package and one app consuming it
- `workspace/complex` — larger workspace fixture with multiple apps, shared packages, and transitive workspace links
- `workspace/nested-boundary` — workspace fixture with a nested non-workspace child package for boundary regressions
- `workspace/cycles` — generated workspace fixture set for pure workspace cycles plus the current default-path external registry re-entry linker failure without registry leakage
- `workspace/rollback` — generated workspace fixture for workspace self-dependency early-abort coverage, asserting the install fails before writing member lockfiles or self-links
- `workspace/multi-member-prompt` — generated workspace fixture for multi-member filtered install coverage, covering streamed `--json` envelopes and the interactive decline-before-write path
- `workspace/targeting` — workspace fixture for `--filter`, `--filter-prod`, `--no-bail`, `--workspace-concurrency`, `--changed-files-ignore-pattern`, `--test-pattern`, `pkg{path}`, `-w`, multi-member writes, uninstall targeting, and `--fail-if-no-match`
- `workspace/pack` — workspace fixture for `lpm pack --all`, root-level tsdown bin reuse, workspace JSON envelopes, and multi-member watch rejection
