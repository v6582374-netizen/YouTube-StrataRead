"""Tiny cross-platform single-key reader built on prompt_toolkit primitives.

We intentionally avoid a full ``Application`` / Layout because the reader UI
mixes blocking streaming output with single-key controls. Instead we read
``KeyPress`` events from a dedicated input in raw mode.

Mouse support is opt-in: passing ``with_mouse=True`` to :func:`key_reader`
toggles xterm's "any-motion" reporting (DEC mode 1003) together with SGR
encoded coordinates (DEC mode 1006). Mouse reports are delivered as
``Key(key="mouse", raw=<raw ESC[ ... >)`` so the caller can decode them via
:mod:`youtube_strataread.reader.mouse`.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import dataclass

from prompt_toolkit.input import create_input
from prompt_toolkit.keys import Keys


@dataclass
class Key:
    key: str  # e.g. "tab", "enter", "escape", "space", "mouse", or a char
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

_ENABLE_MOUSE = "\x1b[?1003h\x1b[?1006h"
_DISABLE_MOUSE = "\x1b[?1003l\x1b[?1006l"


@contextmanager
def key_reader(with_mouse: bool = False):
    """Yield a callable ``read(timeout=None) -> Key | None``.

    ``None`` means the timeout elapsed without any key press. When
    ``timeout`` is ``None`` the read blocks until the user presses something.
    When ``with_mouse=True`` we enable xterm's any-motion + SGR mouse
    reporting on entry and disable it on exit, so hover/click sequences
    surface as ``Key(key="mouse", raw=...)``.
    """
    import select

    inp = create_input()
    try:
        fd = inp.fileno()
    except Exception:
        fd = sys.stdin.fileno()

    mouse_enabled = False
    if with_mouse:
        try:
            tty_ok = sys.stdout.isatty()
        except Exception:
            tty_ok = False
        if tty_ok:
            sys.stdout.write(_ENABLE_MOUSE)
            sys.stdout.flush()
            mouse_enabled = True

    try:
        with inp.raw_mode():
            def read(timeout: float | None = None) -> Key | None:
                # Drain any already-buffered keys first so our users don't
                # miss rapid keystrokes that arrived while rendering.
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
                    if k == Keys.Vt100MouseEvent:
                        return Key(key="mouse", raw=first.data or "")
                    name = _SPECIAL_MAP.get(k, str(k))
                else:
                    name = str(k)
                    if name == " ":
                        name = "space"
                return Key(key=name, raw=first.data or "")

            yield read
    finally:
        if mouse_enabled:
            sys.stdout.write(_DISABLE_MOUSE)
            sys.stdout.flush()
