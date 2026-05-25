# workspace/complex

Larger workspace smoke fixture for multi-member install flows.

Included:

- two apps: `@smoke/web` and `@smoke/docs`
- three shared packages: `@smoke/ui`, `@smoke/tokens`, and `@smoke/config`
- a transitive workspace chain: app -> `@smoke/ui` -> `@smoke/tokens`
- one shared registry dependency reused across apps: `kleur`

Useful smoke checks:

- workspace member discovery across multiple apps and packages
- transitive `workspace:*` linking
- repeated member-cwd installs against different apps
- root-vs-member behavior when running `lpm install` at different levels
