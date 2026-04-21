"""Persistent footer showing breadcrumb context + aurora progress."""
from __future__ import annotations

import os
import sys
import time

_RESET = "\x1b[0m"
_SAVE_CURSOR = "\x1b7"      # DECSC
_RESTORE_CURSOR = "\x1b8"   # DECRC
_CLEAR_LINE = "\x1b[2K"
_HIDE_CURSOR = "\x1b[?25l"
_SHOW_CURSOR = "\x1b[?25h"
_ELLIPSIS = "..."
_BREADCRUMB = "\x1b[38;2;186;240;255m"
_PCT = "\x1b[38;2;214;244;255m"
_EMPTY = "\x1b[38;2;39;64;86m"

_AURORA_STOPS = [
    (86, 236, 255),
    (109, 219, 255),
    (138, 255, 204),
    (191, 248, 158),
    (255, 220, 153),
]


def _char_width(ch: str) -> int:
    if ch == "":
        return 0
    o = ord(ch)
    if 0x4E00 <= o <= 0x9FFF:
        return 2
    if 0x3040 <= o <= 0x30FF:
        return 2
    if 0xFF00 <= o <= 0xFFEF:
        return 2
    if 0x3000 <= o <= 0x303F:
        return 2
    if 0xAC00 <= o <= 0xD7A3:
        return 2
    if o < 0x20:
        return 0
    return 1


def _display_width(text: str) -> int:
    return sum(_char_width(ch) for ch in text)


def _truncate_left(text: str, max_width: int) -> str:
    if max_width <= 0:
        return ""
    if _display_width(text) <= max_width:
        return text
    ellipsis_width = _display_width(_ELLIPSIS)
    if max_width <= ellipsis_width:
        return _ELLIPSIS[:max_width]
    keep: list[str] = []
    width = ellipsis_width
    for ch in reversed(text):
        ch_width = _char_width(ch)
        if width + ch_width > max_width:
            break
        keep.append(ch)
        width += ch_width
    return _ELLIPSIS + "".join(reversed(keep))


def _blend(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(round(a[0] + (b[0] - a[0]) * t)),
        int(round(a[1] + (b[1] - a[1]) * t)),
        int(round(a[2] + (b[2] - a[2]) * t)),
    )


def _aurora_color(t: float) -> tuple[int, int, int]:
    if t <= 0:
        return _AURORA_STOPS[0]
    if t >= 1:
        return _AURORA_STOPS[-1]
    span = len(_AURORA_STOPS) - 1
    scaled = t * span
    idx = min(int(scaled), span - 1)
    local_t = scaled - idx
    return _blend(_AURORA_STOPS[idx], _AURORA_STOPS[idx + 1], local_t)


def _fg(rgb: tuple[int, int, int]) -> str:
    return f"\x1b[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"


class StatusBar:
    """Three-row footer: spacer + breadcrumb + aurora progress."""

    def __init__(self, total_chars: int) -> None:
        self.total_chars = max(total_chars, 1)
        self.done_chars = 0
        self._active = False
        self._last_render = 0.0
        self._enabled = self._detect_tty()
        self._width, self._height = self._detect_size()
        self._context = ""

    def setup(self) -> None:
        if not self._enabled:
            return
        self._width, self._height = self._detect_size()
        if self._height < 5:
            self._enabled = False
            return
        sys.stdout.write(_HIDE_CURSOR)
        sys.stdout.write(f"\x1b[1;{self.content_height}r")
        sys.stdout.write(f"\x1b[{self.content_height};1H")
        sys.stdout.flush()
        self._active = True
        self._render(force=True)

    def teardown(self) -> None:
        if not self._active:
            return
        sys.stdout.write("\x1b[r")
        sys.stdout.write(_SAVE_CURSOR)
        for row in (self._spacer_row, self._breadcrumb_row, self._progress_row):
            sys.stdout.write(f"\x1b[{row};1H")
            sys.stdout.write(_CLEAR_LINE)
        sys.stdout.write(_RESTORE_CURSOR)
        sys.stdout.write(_SHOW_CURSOR)
        sys.stdout.flush()
        self._active = False

    def update(self, delta_chars: int) -> None:
        if delta_chars <= 0:
            return
        self.done_chars = min(self.done_chars + delta_chars, self.total_chars)
        self._render()

    def set_progress(self, done_chars: int) -> None:
        self.done_chars = max(0, min(done_chars, self.total_chars))
        self._render(force=True)

    def refresh(self) -> None:
        self._render(force=True)

    def set_context(self, text: str) -> None:
        self._context = text.strip()
        self._render(force=True)

    @property
    def content_height(self) -> int:
        return max(self._height - 3, 1) if self._enabled else self._height

    @property
    def width(self) -> int:
        return self._width

    @property
    def _spacer_row(self) -> int:
        return self._height - 2

    @property
    def _breadcrumb_row(self) -> int:
        return self._height - 1

    @property
    def _progress_row(self) -> int:
        return self._height

    def _render(self, force: bool = False) -> None:
        if not self._active:
            return
        now = time.monotonic()
        if not force and self.done_chars < self.total_chars and now - self._last_render < 1 / 30:
            return
        self._last_render = now

        breadcrumb = _truncate_left(self._context, self._width)
        progress = self._progress_line()

        sys.stdout.write(_SAVE_CURSOR)

        sys.stdout.write(f"\x1b[{self._spacer_row};1H")
        sys.stdout.write(_CLEAR_LINE)

        sys.stdout.write(f"\x1b[{self._breadcrumb_row};1H")
        sys.stdout.write(_CLEAR_LINE)
        sys.stdout.write(_BREADCRUMB)
        sys.stdout.write(breadcrumb)
        sys.stdout.write(_RESET)

        sys.stdout.write(f"\x1b[{self._progress_row};1H")
        sys.stdout.write(_CLEAR_LINE)
        sys.stdout.write(progress)
        sys.stdout.write(_RESET)

        sys.stdout.write(_RESTORE_CURSOR)
        sys.stdout.flush()

    def _progress_line(self) -> str:
        pct = self.done_chars / self.total_chars
        pct_text = f"{int(pct * 100):3d}%"
        available = self._width - _display_width(pct_text) - 1
        if available <= 0:
            return _PCT + _truncate_left(pct_text, self._width)
        bar_width = available
        filled = min(bar_width, max(0, int(round(bar_width * pct))))

        cells: list[str] = []
        for idx in range(bar_width):
            if idx < filled:
                t = idx / max(filled - 1, 1) if filled > 1 else 0.0
                rgb = _aurora_color(t)
                if idx == filled - 1:
                    rgb = _blend(rgb, (255, 255, 255), 0.25)
                cells.append(_fg(rgb) + "█")
            else:
                cells.append(_EMPTY + "▁")
        return "".join(cells) + _RESET + " " + _PCT + pct_text

    @staticmethod
    def _detect_tty() -> bool:
        try:
            return sys.stdout.isatty()
        except Exception:
            return False

    @staticmethod
    def _detect_size() -> tuple[int, int]:
        try:
            size = os.get_terminal_size()
            return size.columns, size.lines
        except OSError:
            return 80, 24


class NullStatusBar:
    """Drop-in replacement used when the footer should be skipped entirely."""

    total_chars = 0
    done_chars = 0

    def setup(self) -> None:
        return

    def teardown(self) -> None:
        return

    def update(self, delta_chars: int) -> None:
        return

    def set_progress(self, done_chars: int) -> None:
        return

    def refresh(self) -> None:
        return

    def set_context(self, text: str) -> None:
        return

    @property
    def content_height(self) -> int:
        return 24

    @property
    def width(self) -> int:
        return 80
