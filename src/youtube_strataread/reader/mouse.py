"""SGR (1006) xterm mouse-event parser.

prompt_toolkit already detects the escape sequence and bubbles it up as
``Keys.Vt100MouseEvent``; the raw payload is in ``KeyPress.data``. We decode
the shape ``\\x1b[<Cb;Cx;Cy[M|m]`` into a tiny :class:`MouseEvent` struct so
the reader UI layer can stay dumb about wire format.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ``ESC [ < Cb ; Cx ; Cy M|m``  (SGR mouse reporting, DEC mode 1006)
_SGR_RE = re.compile(r"^\x1b\[<(\d+);(\d+);(\d+)([Mm])$")


@dataclass(frozen=True)
class MouseEvent:
    """Decoded xterm SGR mouse report.

    Attributes:
        kind: ``"move"`` for pointer motion, ``"press"`` for button-down,
            ``"release"`` for button-up. Wheel events surface as ``"press"``
            with ``button`` in {64, 65}.
        button: ``0``=left, ``1``=middle, ``2``=right (ignoring motion flag).
        row: 1-indexed terminal row.
        col: 1-indexed terminal column.
    """

    kind: str
    button: int
    row: int
    col: int


def parse(raw: str) -> MouseEvent | None:
    """Return a :class:`MouseEvent` or ``None`` if ``raw`` isn't SGR mouse.

    We intentionally ignore legacy X10 mouse reporting (``ESC[M...``) because
    we only ever enable ``?1006`` (SGR) alongside ``?1003`` (all-motion).
    """
    m = _SGR_RE.match(raw)
    if not m:
        return None
    cb = int(m.group(1))
    col = int(m.group(2))
    row = int(m.group(3))
    terminator = m.group(4)
    button = cb & 0x3
    if cb & 32:
        kind = "move"
    elif terminator == "M":
        kind = "press"
    else:
        kind = "release"
    # Wheel: cb has bit 64 set; surface raw cb as button so callers can filter.
    if cb & 64:
        button = cb
    return MouseEvent(kind=kind, button=button, row=row, col=col)
