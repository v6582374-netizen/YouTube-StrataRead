"""Persistent bottom-of-terminal reading-progress bar.

Implementation uses DEC's scrolling region (``DECSTBM``) to carve off the
very last terminal row as a sticky footer. The rest of the screen scrolls
normally inside rows ``1 .. height-1``; the footer on row ``height`` is
refreshed with a ``saved-cursor \u2192 jump \u2192 restore-cursor`` dance so
sentence streaming isn't disturbed.

When ``stdout`` isn't a TTY we silently become a no-op so the reader still
works under pipes / test harnesses.
"""
from __future__ import annotations

import os
import sys
import time

_CHAMPAGNE = "\x1b[38;2;247;231;172m"
_DIM_CYAN = "\x1b[2;36m"
_RESET = "\x1b[0m"
_SAVE_CURSOR = "\x1b7"      # DECSC
_RESTORE_CURSOR = "\x1b8"   # DECRC
_CLEAR_LINE = "\x1b[2K"


class StatusBar:
    """Bottom-row progress bar for the interactive reader.

    Usage::

        bar = StatusBar(total_chars=sum(len(leaf.body) for leaf in ...))
        bar.setup()
        try:
            bar.update(delta_chars=len(chunk))
        finally:
            bar.teardown()
    """

    def __init__(self, total_chars: int) -> None:
        self.total_chars = max(total_chars, 1)
        self.done_chars = 0
        self._active = False
        self._last_render = 0.0
        self._enabled = self._detect_tty()
        self._width, self._height = self._detect_size()

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def setup(self) -> None:
        """Install the scrolling region and draw the initial footer."""
        if not self._enabled:
            return
        self._width, self._height = self._detect_size()
        if self._height < 3:
            # Too short to meaningfully reserve a footer; disable silently.
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
        sys.stdout.write("\x1b[r")  # reset scrolling region
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
        """Advance the progress by ``delta_chars`` and maybe re-render."""
        if delta_chars <= 0:
            return
        self.done_chars = min(self.done_chars + delta_chars, self.total_chars)
        self._render()

    def set_progress(self, done_chars: int) -> None:
        self.done_chars = max(0, min(done_chars, self.total_chars))
        self._render(force=True)

    def refresh(self) -> None:
        self._render(force=True)

    # ------------------------------------------------------------------
    # geometry
    # ------------------------------------------------------------------
    @property
    def content_height(self) -> int:
        """Rows available for content (i.e. excluding the footer)."""
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
        if not force and self.done_chars < self.total_chars:
            if now - self._last_render < 1 / 30:  # cap at ~30 FPS
                return
        self._last_render = now
        pct = self.done_chars / self.total_chars
        # Reserve 10 cols for the "[] NNN%" wrapper + trailing space.
        bar_width = max(self._width - 10, 10)
        filled = int(round(bar_width * pct))
        filled = min(bar_width, max(0, filled))
        bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
        pct_text = f"{int(pct * 100):3d}%"
        label = f"[{bar}] {pct_text}"
        if len(label) > self._width:
            label = label[: self._width]
        sys.stdout.write(_SAVE_CURSOR)
        sys.stdout.write(f"\x1b[{self._height};1H")
        sys.stdout.write(_CLEAR_LINE)
        sys.stdout.write(_DIM_CYAN)
        sys.stdout.write(label)
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

    def setup(self) -> None:  # noqa: D401 - trivial
        return

    def teardown(self) -> None:
        return

    def update(self, delta_chars: int) -> None:
        return

    def set_progress(self, done_chars: int) -> None:
        return

    def refresh(self) -> None:
        return

    @property
    def content_height(self) -> int:
        return 24

    @property
    def width(self) -> int:
        return 80
