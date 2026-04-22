"""Persistent footer showing wrapped breadcrumb context + reading progress."""
from __future__ import annotations

import os
import sys
import time

_DIM_CYAN = "\x1b[2;36m"
_RESET = "\x1b[0m"
_SAVE_CURSOR = "\x1b7"      # DECSC
_RESTORE_CURSOR = "\x1b8"   # DECRC
_CLEAR_LINE = "\x1b[2K"
_HIDE_CURSOR = "\x1b[?25l"
_SHOW_CURSOR = "\x1b[?25h"


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


def _wrap_text(text: str, width: int) -> list[str]:
    if width <= 0:
        return [""]
    if not text:
        return [""]

    lines: list[str] = []
    current: list[str] = []
    current_width = 0
    for ch in text:
        if ch == "\n":
            lines.append("".join(current))
            current = []
            current_width = 0
            continue
        ch_width = _char_width(ch)
        if current and current_width + ch_width > width:
            lines.append("".join(current))
            current = []
            current_width = 0
        current.append(ch)
        current_width += ch_width
    lines.append("".join(current))
    return lines or [""]


class StatusBar:
    """Sticky footer with a spacer row, wrapped breadcrumb rows, and progress."""

    def __init__(self, total_chars: int, *, contexts: list[str] | None = None) -> None:
        self.total_chars = max(total_chars, 1)
        self.done_chars = 0
        self._active = False
        self._last_render = 0.0
        self._enabled = self._detect_tty()
        self._width, self._height = self._detect_size()
        self._context = ""
        self._context_lines = [""]
        self._reserved_context_rows = 1
        self._footer_height = 3
        self._contexts = [text.strip() for text in (contexts or []) if text.strip()]
        self._sync_layout()

    def setup(self) -> None:
        if not self._enabled:
            return
        self._sync_layout()
        if self.content_height < 1:
            self._enabled = False
            return
        sys.stdout.write(_HIDE_CURSOR)
        self._apply_scroll_region(move_cursor=True)
        sys.stdout.flush()
        self._active = True
        self._render(force=True)

    def teardown(self) -> None:
        if not self._active:
            return
        sys.stdout.write("\x1b[r")
        sys.stdout.write(_SAVE_CURSOR)
        for row in range(self.content_height + 1, self._height + 1):
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
        if not self._enabled:
            return self._height
        return max(self._height - self._footer_height, 1)

    @property
    def width(self) -> int:
        return self._width

    def _render(self, force: bool = False) -> None:
        if not self._active:
            self._sync_layout()
            return
        now = time.monotonic()
        if not force and self.done_chars < self.total_chars and now - self._last_render < 1 / 30:
            return
        self._last_render = now
        self._sync_layout()

        sys.stdout.write(_SAVE_CURSOR)

        sys.stdout.write(f"\x1b[{self._spacer_row};1H")
        sys.stdout.write(_CLEAR_LINE)

        for idx in range(self._reserved_context_rows):
            row = self._breadcrumb_start_row + idx
            sys.stdout.write(f"\x1b[{row};1H")
            sys.stdout.write(_CLEAR_LINE)
            if idx < len(self._context_lines):
                sys.stdout.write(_DIM_CYAN)
                sys.stdout.write(self._context_lines[idx])
                sys.stdout.write(_RESET)

        sys.stdout.write(f"\x1b[{self._progress_row};1H")
        sys.stdout.write(_CLEAR_LINE)
        sys.stdout.write(_DIM_CYAN)
        sys.stdout.write(self._progress_line())
        sys.stdout.write(_RESET)

        sys.stdout.write(_RESTORE_CURSOR)
        sys.stdout.flush()

    @property
    def _spacer_row(self) -> int:
        return self.content_height + 1

    @property
    def _breadcrumb_start_row(self) -> int:
        return self.content_height + 2

    @property
    def _progress_row(self) -> int:
        return self._height

    def _progress_line(self) -> str:
        pct = self.done_chars / self.total_chars
        pct_text = f"{int(pct * 100):3d}%"
        bar_width = max(min(self._width // 3, self._width - 12), 8)
        filled = int(round(bar_width * pct))
        filled = min(bar_width, max(0, filled))
        bar = "█" * filled + "░" * (bar_width - filled)
        progress = f"[{bar}] {pct_text}"
        if _display_width(progress) <= self._width:
            return progress
        if self._width <= len(pct_text):
            return pct_text[-self._width :]
        bar_width = max(self._width - len(pct_text) - 3, 1)
        filled = int(round(bar_width * pct))
        filled = min(bar_width, max(0, filled))
        bar = "█" * filled + "░" * (bar_width - filled)
        return f"[{bar}] {pct_text}"

    def _sync_layout(self) -> None:
        width, height = self._detect_size()
        self._width = width
        self._height = height
        if self._height < 4:
            self._enabled = False
            return

        context_lines = _wrap_text(self._context, self._width)
        max_context_rows = max(self._height - 2, 1)
        reserved_context_rows = min(self._max_context_rows(self._width), max_context_rows)
        if len(context_lines) > reserved_context_rows:
            context_lines = context_lines[-reserved_context_rows:]
        footer_height = reserved_context_rows + 2

        layout_changed = (
            reserved_context_rows != self._reserved_context_rows
            or footer_height != self._footer_height
        )
        self._context_lines = context_lines
        self._reserved_context_rows = reserved_context_rows
        self._footer_height = footer_height
        if self._active and layout_changed:
            self._apply_scroll_region(move_cursor=False)

    def _max_context_rows(self, width: int) -> int:
        contexts = self._contexts or [self._context]
        return max(len(_wrap_text(text, width)) for text in contexts) or 1

    def _apply_scroll_region(self, *, move_cursor: bool) -> None:
        sys.stdout.write(f"\x1b[1;{self.content_height}r")
        if move_cursor:
            sys.stdout.write("\x1b[1;1H")

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
