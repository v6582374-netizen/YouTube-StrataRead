#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
sidecar="$script_dir/src-tauri/target/release/bundle/macos/视频资料库.app/Contents/MacOS/youtube-workbench-sidecar"
workspace=$(mktemp -d /tmp/youtube-workbench-bundle-smoke.XXXXXX)
trap 'rm -rf "$workspace"' EXIT
response="$workspace/response.json"

if [ ! -x "$sidecar" ]; then
  echo "Build the macOS application before running this smoke test." >&2
  exit 1
fi

printf '%s\n' '{"id":"bundle","capability":"library.snapshot","arguments":{}}' |
  env -i HOME="$HOME" YOUTUBE_WORKBENCH_WORKSPACE="$workspace/workspace" "$sidecar" > "$response"

grep -q '"id": "bundle"' "$response"
grep -q '"ok": true' "$response"
test -f "$workspace/workspace/workspace.sqlite3"
echo "bundled sidecar smoke test passed"
