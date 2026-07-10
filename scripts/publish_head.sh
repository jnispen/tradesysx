#!/usr/bin/env bash
set -euo pipefail

label="${1:-head}"
image="tradesysx-$label"
zip="tradesysx-$label.zip"
repo="mooncat911/$image"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(git -C "$script_dir" rev-parse --show-toplevel)"

"$script_dir/export_package.sh" "$label"
docker build -t "$image" -f "$script_dir/Dockerfile" --build-arg ZIP_FILE="$zip" "$repo_root/dist"
docker tag "$image:latest" "$repo:latest"
docker push "$repo:latest"
