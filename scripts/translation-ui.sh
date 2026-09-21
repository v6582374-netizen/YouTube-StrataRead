#!/bin/sh
# Optional upstream UI; uses relocated source, never a nested checkout.
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec uv run --no-project --with-requirements "$ROOT/packaging/translation-ui-requirements.txt" python -m translation_agent.webui.app "$@"
