# install/download/basic

Local `lpm download` command smoke fixture.

The runner downloads one package from the mock registry into a custom output directory and verifies the docs contract for read-only extraction.

Current checks:

- `lpm download smoke-download-lib --version 1.2.0 --json --output nested/../download-out` returns a JSON envelope with a canonical absolute `output_dir`.
- extraction strips the tarball's top-level `package/` directory so files land directly in `download-out/`.
- integrity is verified and the output includes extracted package files.
- the command leaves `package.json`, `node_modules`, lockfiles, and the global content-addressable store untouched.
- lifecycle scripts are not executed during download.

Relevant runner entry:

- `python3 run_smokes.py install-download`
