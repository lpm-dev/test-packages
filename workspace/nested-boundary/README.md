# workspace/nested-boundary

Workspace smoke fixture focused on nested `package.json` boundaries.

Included:

- one app: `@smoke/studio`
- two shared workspace packages: `@smoke/ui` and `@smoke/tokens`
- one nested non-workspace child package under the app tree
- one real registry dependency at the app layer: `kleur`

Useful smoke checks:

- workspace-member installs from inside the app directory
- nested `package.json` boundary handling during phantom scanning
- mixed workspace + registry linking without nested-child leakage
