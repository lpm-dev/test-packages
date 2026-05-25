# install/query/basic

Local `lpm query` command smoke fixture.

The runner installs three mock-registry packages into an LPM-managed project:

- `query-eval-pkg` carries a real `eval(...)` call.
- `query-network-pkg` makes an outbound `fetch(...)` call.
- `query-clean-pkg` is the clean control package.

Current checks:

- `lpm query :eval` isolates the eval-backed package.
- `lpm query ":root > :network"` finds the direct network dependency.
- `lpm query :eval --assert-none` fails non-zero when the selector matches.
- `lpm query --count --json` emits tag-count data.
- `lpm query :eval --format mermaid` renders a dependency subgraph for an LPM-managed project.

Relevant runner entry:

- `python3 run_smokes.py install-query`
