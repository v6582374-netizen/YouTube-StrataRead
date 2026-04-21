"""Persistent footer showing breadcrumb context + reading progress.

Implementation uses DEC's scrolling region (``DECSTBM``) to reserve the very
last terminal row as a sticky footer. The content area lives in rows
``1 .. height-1`` while the footer continuously shows the current chapter
breadcrumb on the left and the whole-document progress on the right.

When ``stdout`` isn't a TTY we silently become a no-op so the reader still
works under pipes / test harnesses.
"""
from __future__ import annotations

import os
import sys
import time

_DIM_CYAN = "\x1b[2;36m"
_RESET = "\x1b[0m"
_SAVE_CURSOR = "\x1b7"      # DECSC
_RESTORE_CURSOR = "\x1b8"   # DECRC
_CLEAR_LINE = "\x1b[2K"
_ELLIPSIS = "..."


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


class StatusBar:
    """Bottom-row footer for the interactive reader."""

    def __init__(self, total_chars: int) -> None:
        self.total_chars = max(total_chars, 1)
        self.done_chars = 0
        self._active = False
        self._last_render = 0.0
        self._enabled = self._detect_tty()
        self._width, self._height = self._detect_size()
        self._context = ""

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def setup(self) -> None:
        """Install the scrolling region and draw the initial footer."""
        if not self._enabled:
            return
        self._width, self._height = self._detect_size()
        if self._height < 3:
            self._enabled = False
            return
        sys.stdout.write(f"\x1b[1;{self._height - 1}r")
        sys.stdout.write("\x1b[1;1H")
        sys.stdout.flush()
        self._active = True
        self._render(force=True)

    def teardown(self) -> None:
        """Restore the full scrolling region and wipe the footer."""
        if not self._active:
            return
        sys.stdout.write("\x1b[r")
        sys.stdout.write(_SAVE_CURSOR)
        sys.stdout.write(f"\x1b[{self._height};1H")
        sys.stdout.write(_CLEAR_LINE)
        sys.stdout.write(_RESTORE_CURSOR)
        sys.stdout.flush()
        self._active = False

    # ------------------------------------------------------------------
    # progress reporting
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # geometry
    # ------------------------------------------------------------------
    @property
    def content_height(self) -> int:
        return max(self._height - 1, 1) if self._enabled else self._height

    @property
    def width(self) -> int:
        return self._width

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _render(self, force: bool = False) -> None:
        if not self._active:
            return
        now = time.monotonic()
        if not force and self.done_chars < self.total_chars and now - self._last_render < 1 / 30:
            return
        self._last_render = now

        pct = self.done_chars / self.total_chars
        pct_text = f"{int(pct * 100):3d}%"
        bar_width = max(min(self._width // 3, self._width - 12), 8)
        filled = int(round(bar_width * pct))
        filled = min(bar_width, max(0, filled))
        bar = "█" * filled + "░" * (bar_width - filled)
        progress = f"[{bar}] {pct_text}"
        progress_width = _display_width(progress)

        line = progress
        if self._context and progress_width + 2 < self._width:
            available = self._width - progress_width - 2
            context = _truncate_left(self._context, available)
            pad = max(self._width - progress_width - _display_width(context), 0)
            line = context + (" " * pad) + progress
        elif progress_width < self._width:
            line = (" " * (self._width - progress_width)) + progress

        if _display_width(line) > self._width:
            line = _truncate_left(line, self._width)

        sys.stdout.write(_SAVE_CURSOR)
        sys.stdout.write(f"\x1b[{self._height};1H")
        sys.stdout.write(_CLEAR_LINE)
        sys.stdout.write(_DIM_CYAN)
        sys.stdout.write(line)
        sys.stdout.write(_RESET)
        sys.stdout.write(_RESTORE_CURSOR)
        sys.stdout.flush()

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
