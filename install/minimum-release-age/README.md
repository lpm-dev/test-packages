# minimum-release-age smoke fixtures

Fixture group for the recent-publish cooldown gate:

- default 24h block for recently published packages
- `--allow-new` bypass for the current install
- `--min-release-age=0` disables the cooldown for the current install
- explicit pinned specs still do not bypass the cooldown

Runner entry:

- `python3 run_smokes.py install-minimum-release-age`
