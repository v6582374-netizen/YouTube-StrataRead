"""Tiny cross-platform single-key reader built on prompt_toolkit primitives.

We intentionally avoid a full ``Application`` / Layout because the reader UI
mixes blocking streaming output with single-key controls. Instead we read
``KeyPress`` events from a dedicated input in raw mode.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

from prompt_toolkit.input import create_input
from prompt_toolkit.keys import Keys


@dataclass
class Key:
    key: str  # e.g. "tab", "enter", "escape", "space", or a printable char
    raw: str


_SPECIAL_MAP = {
    Keys.Tab: "tab",
    Keys.BackTab: "shift-tab",
    Keys.Enter: "enter",
    Keys.ControlM: "enter",
    Keys.ControlJ: "enter",
    Keys.Escape: "escape",
    Keys.Up: "up",
    Keys.Down: "down",
    Keys.Left: "left",
    Keys.Right: "right",
    Keys.Backspace: "backspace",
    Keys.ControlC: "ctrl-c",
}


@contextmanager
def key_reader():
    """Yield a callable ``read(timeout=None) -> Key | None``.

    ``None`` means the timeout elapsed without any key press. When ``timeout``
    is ``None`` the read blocks until the user presses something.
    """
    import select
    import sys

    inp = create_input()
    try:
        fd = inp.fileno()
    except Exception:
        fd = sys.stdin.fileno()

    with inp.raw_mode():
        def read(timeout: float | None = None) -> Key | None:
            # Drain any already-buffered keys first so our users don't miss
            # rapid keystrokes that arrived while we were rendering.
            keys = inp.read_keys()
            if not keys:
                r, _, _ = select.select([fd], [], [], timeout)
                if not r:
                    return None
                keys = inp.read_keys()
            if not keys:
                return None
            first = keys[0]
            k = first.key
            if isinstance(k, Keys):
                name = _SPECIAL_MAP.get(k, str(k))
            else:
                name = str(k)
                if name == " ":
                    name = "space"
            return Key(key=name, raw=first.data or "")

        yield read
