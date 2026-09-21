"""PyInstaller entry point for the bundled desktop sidecar server.

Thin wrapper so PyInstaller has a concrete script to analyze (the console_script
`openworker-server` is generated metadata, not a file). Runs the same `main()`.
"""

import os
import sys

if getattr(sys, "frozen", False):
    os.environ.setdefault("TIKTOKEN_CACHE_DIR", os.path.join(sys._MEIPASS, "translation-tokenizer-cache"))

from coworker.server.run import main

if __name__ == "__main__":
    main()
