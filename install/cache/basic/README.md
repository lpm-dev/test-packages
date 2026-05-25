Direct `lpm cache` smoke fixture.

- `run_smokes.py install-cache` seeds an isolated `LPM_HOME`, then drives `lpm cache path`, `lpm cache clear tasks`, and `lpm cache clean`.
- Assertions pin the documented cache-store split: metadata/tasks/dlx entries are removed, while a seeded store marker under `store/v1/` survives byte-for-byte.
- The fixture project itself stays minimal because the command contract is global-cache state, not project dependency resolution.
