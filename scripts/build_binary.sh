#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

pyinstaller --clean --noconfirm tradesysx.spec

# The app reads config/, quotes/ and out/ relative to its working directory
# (RunContext.basedir), not from PyInstaller's bundled data, so they need to
# live alongside the binary.
cp -r config "$repo_root/dist/"
cp -r quotes "$repo_root/dist/"
mkdir -p "$repo_root/dist/out"

echo "Built $repo_root/dist/tradesysx"
echo "Run it from $repo_root/dist/ (or copy that whole directory elsewhere)"
