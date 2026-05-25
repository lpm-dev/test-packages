# read-only-routing/basic

Baseline consumer fixture for `.npmrc`-routed read-only command smokes.

The smoke runner rewrites `.npmrc`, talks to a local mock registry that serves
only npm-style metadata and search endpoints, and verifies that `lpm info`,
`lpm resolve`, `lpm search`, and `lpm download` all follow the project-local
registry route.
