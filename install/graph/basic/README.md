# install/graph/basic

Direct smoke fixture for `python3 run_smokes.py install-graph`.

The scenario covers the current local `lpm graph` contract:

- default tree output prints resolved `name@version` nodes, not manifest ranges
- `--filter` is substring-based (`press` matches `express`)
- `--depth` prunes the graph before json, stats, and html rendering
- `--format html --no-open` writes `.lpm/graph.html` without launching a browser
- `--no-open` without `--format html` warns only on the human surface
