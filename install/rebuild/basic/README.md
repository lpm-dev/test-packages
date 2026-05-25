# install/rebuild/basic

Local `lpm rebuild` command smoke fixture.

The runner installs one package with a real `postinstall` script under the default deny policy, approves it through `lpm approve-scripts`, and then exercises named rebuild behavior against the installed package.

Current checks:

- `lpm rebuild <pkg> --dry-run --json` selects the approved package and reports it as trusted.
- `lpm rebuild <pkg>` executes the lifecycle script and writes the first build counter.
- a second `lpm rebuild <pkg>` reports the package as already built and leaves the counter unchanged.
- `lpm rebuild <pkg> --force` re-runs the script and increments the counter again.

Relevant runner entry:

- `python3 run_smokes.py install-rebuild`
