#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
output_dir="$script_dir/src-tauri/binaries"
work_dir="$script_dir/.sidecar-build"
target_name="youtube-workbench-sidecar-aarch64-apple-darwin"

rm -rf "$output_dir" "$work_dir"
mkdir -p "$output_dir" "$work_dir"
uv run --python 3.13 --with pyinstaller==6.22.3 pyinstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name youtube-workbench-sidecar \
  --paths "$script_dir/../src" \
  --distpath "$work_dir/dist" \
  --workpath "$work_dir/work" \
  --specpath "$work_dir/spec" \
  "$script_dir/sidecar_entry.py"
mv "$work_dir/dist/youtube-workbench-sidecar" "$output_dir/$target_name"
