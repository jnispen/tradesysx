#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
    echo "Usage: $0 <label>" >&2
    exit 1
fi

label="$1"
repo_root="$(git rev-parse --show-toplevel)"
dist_dir="$repo_root/dist"
out_zip="$dist_dir/getquotes-$label.zip"

if [ -n "$(git -C "$repo_root" status --porcelain)" ]; then
    echo "Warning: working tree has uncommitted changes; the export reflects the last commit only:" >&2
    git -C "$repo_root" status --porcelain >&2
fi

mkdir -p "$dist_dir"
rm -f "$out_zip"
git -C "$repo_root" archive --format=zip --prefix=getquotes/ --output="$out_zip" HEAD

echo "Created $out_zip"
