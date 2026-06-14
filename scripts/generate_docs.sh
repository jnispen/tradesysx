#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
docs_dir="$repo_root/docs"

rm -rf "$docs_dir"
python3 -m pdoc -o "$docs_dir" \
    "$repo_root/context.py" \
    "$repo_root/getquotes.py" \
    "$repo_root/logging_setup.py" \
    "$repo_root/strategy.py" \
    "$repo_root/tables.py" \
    "$repo_root/utils.py" \
    "$repo_root/tst/simulator.py"

echo "Generated docs in $docs_dir/index.html"
