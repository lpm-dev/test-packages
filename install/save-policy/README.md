# save-policy smoke fixtures

Mock-registry fixtures for `lpm install` save-spec behavior.

Covered by `python3 ../../run_smokes.py install-save-policy` from this directory, or `python3 run_smokes.py install-save-policy` from the `test-packages/` root.

Current checks:

- bare install saves the default `^` range
- explicit exact versions stay exact
- explicit semver ranges stay unchanged
- `@latest` saves the resolved default range
- non-latest dist-tags save the resolved exact version when they point at a prerelease
- prereleases save exact
- `@*` stays `*`
- re-installing an existing dependency does not rewrite an existing saved range
