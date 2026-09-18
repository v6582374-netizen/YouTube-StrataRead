#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
uv sync --all-extras
uv run --no-project --with pillow python packaging/generate_icons.py
uv run --all-extras --with pyinstaller python -m PyInstaller --noconfirm packaging/openworker-server.spec
mkdir -p surfaces/gui/src-tauri/binaries
python3 - <<'PY'
import shutil
from pathlib import Path
source = Path('dist/openworker-server')
assert source.is_dir()
target = Path('surfaces/gui/src-tauri/binaries/sidecar')
# Replace the generated bundle, never a user workspace.
if target.exists(): shutil.rmtree(target)
shutil.copytree(source, target)
PY
npm --prefix surfaces/gui ci
cd surfaces/gui
npm run tauri build -- --bundles app
open src-tauri/target/release/bundle/macos/Edison.app
