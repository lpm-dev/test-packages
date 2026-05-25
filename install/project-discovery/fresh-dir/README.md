# install/project-discovery/fresh-dir

Parent fixture for the fresh-directory auto-manifest case.

`empty/` intentionally starts without a `package.json`; the smoke runner resets
that directory before each run and asserts `lpm install <pkg>` creates the
manifest in place.
