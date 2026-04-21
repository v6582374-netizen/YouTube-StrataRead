"""Shared state for the interactive reader.

The session threads four concerns together so ``manual_reader`` and
``stream_reader`` don't have to re-implement each one:

1. **Character budget / progress bar** \u2013 we pre-compute the total visible
   character count across every leaf (``total_chars``) and poke the
   :class:`StatusBar` whenever bytes are handed to the terminal.
2. **Cursor bookkeeping** \u2013 printing a single codepoint updates
   ``(abs_row, col)`` in screen-equivalent units so we can redraw later.
3. **Sentence spans** \u2013 as characters stream, :meth:`write_char` stitches
   them into :class:`SentenceSpan` records covering the screen rectangles
   where each clause landed.
4. **Highlights** \u2013 mouse click and keyboard ``h`` toggle a span's gold
   status; the ordered list is dumped to ``highlights.md`` at shutdown.

Scrolling is cooperative with DEC's scrolling region (``status_bar.setup``
pins the last row): once the active ``abs_row`` would exceed ``content_height``
we bump ``scroll_offset`` by one so span geometry survives the shift.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from youtube_strataread.reader.doc_tree import Node
from youtube_strataread.reader.status_bar import NullStatusBar, StatusBar

# Colour palette -------------------------------------------------------------
# We keep the sequences here so both the live renderer and the hover/highlight
# redraw use identical codes.
_ANSI_RESET = "\x1b[0m"
_ANSI_BOLD_ON = "\x1b[1m"
_ANSI_BOLD_OFF = "\x1b[22m"
_ANSI_DEFAULT_FG = "\x1b[39m"
_ANSI_GRAY = "\x1b[38;5;244m"
_ANSI_GOLD = "\x1b[38;2;247;231;172m"


def _char_width(ch: str) -> int:
    """Very small east-asian-width approximation sufficient for our use."""
    if ch == "":
        return 0
    o = ord(ch)
    if 0x4E00 <= o <= 0x9FFF:  # CJK Unified Ideographs
        return 2
    if 0x3040 <= o <= 0x30FF:  # Hiragana / Katakana
        return 2
    if 0xFF00 <= o <= 0xFFEF:  # Fullwidth forms
        return 2
    if 0x3000 <= o <= 0x303F:  # CJK symbols and punctuation
        return 2
    if 0xAC00 <= o <= 0xD7A3:  # Hangul syllables
        return 2
    if o < 0x20:  # control chars don't take visible cells here
        return 0
    return 1


@dataclass
class SentenceSegment:
    """One on-screen row worth of a sentence (sentences can wrap)."""

    abs_row: int
    start_col: int
    end_col: int  # inclusive (last cell written)


@dataclass
class SentenceSpan:
    leaf_path: str
    leaf_title: str
    sent_idx: int
    text: str
    pieces: list[tuple[str, bool]] = field(default_factory=list)  # (ch, is_bold)
    segments: list[SentenceSegment] = field(default_factory=list)
    highlighted: bool = False

    def contains(self, row: int, col: int) -> bool:
        for seg in self.segments:
            if seg.abs_row == row and seg.start_col <= col <= seg.end_col:
                return True
        return False


@dataclass
class ReadingSession:
    root: Node
    folder: Path
    doc_title: str
    total_chars: int
    status_bar: StatusBar | NullStatusBar

    # ----- cursor state (updated by write_char) -----
    abs_row: int = 1
    col: int = 1
    scroll_offset: int = 0

    # ----- per-leaf state -----
    current_leaf: Node | None = None
    spans: list[SentenceSpan] = field(default_factory=list)
    _current_span: SentenceSpan | None = None

    # ----- hover / highlight state -----
    hovered: SentenceSpan | None = None
    highlights_order: list[SentenceSpan] = field(default_factory=list)

    # ----- progress bookkeeping -----
    done_chars: int = 0
    _leaf_reported_chars: int = 0

    # ------------------------------------------------------------------
    # geometry helpers
    # ------------------------------------------------------------------
    @property
    def content_width(self) -> int:
        return max(self.status_bar.width, 20)

    @property
    def content_height(self) -> int:
        return max(self.status_bar.content_height, 5)

    def visible_row(self, abs_row: int) -> int:
        return abs_row - self.scroll_offset

    # ------------------------------------------------------------------
    # leaf lifecycle
    # ------------------------------------------------------------------
    def begin_leaf(self, leaf: Node, *, header_rows: int) -> None:
        """Declare that a new leaf is about to be rendered.

        ``header_rows`` is how many rows the caller already wrote (title,
        hint, blank line). The next character's ``abs_row`` will be
        ``header_rows + 1``.
        """
        self.current_leaf = leaf
        self.spans = []
        self._current_span = None
        self.hovered = None
        self.scroll_offset = 0
        self.abs_row = header_rows + 1
        self.col = 1
        self._leaf_reported_chars = 0

    def finish_leaf(self) -> None:
        """Flush the current leaf's remaining char-budget to the progress bar.

        Sentence split inserts whitespace we don't literally type, so the
        progress bar gets slightly under-reported during streaming; this
        method tops up the delta so 100% aligns with the last leaf.
        """
        if self.current_leaf is None:
            return
        # Match doc_tree's body length (that's how total_chars was summed).
        total = len(self.current_leaf.body or "")
        if self._leaf_reported_chars < total:
            delta = total - self._leaf_reported_chars
            self.done_chars = min(self.done_chars + delta, self.total_chars)
            self.status_bar.update(delta)
            self._leaf_reported_chars = total

    # ------------------------------------------------------------------
    # sentence boundaries
    # ------------------------------------------------------------------
    def begin_sentence(self, sent_idx: int, text: str) -> SentenceSpan:
        assert self.current_leaf is not None, "begin_leaf must run first"
        span = SentenceSpan(
            leaf_path=self.current_leaf.path,
            leaf_title=self.current_leaf.title,
            sent_idx=sent_idx,
            text=text,
            segments=[
                SentenceSegment(
                    abs_row=self.abs_row,
                    start_col=self.col,
                    end_col=self.col - 1,  # empty until first char lands
                )
            ],
        )
        self._current_span = span
        return span

    def end_sentence(self) -> None:
        if self._current_span is None:
            return
        span = self._current_span
        # Drop an empty trailing segment (happens when sentence ends exactly
        # at a wrap boundary).
        if span.segments and span.segments[-1].end_col < span.segments[-1].start_col:
            span.segments.pop()
        if span.segments:
            self.spans.append(span)
        self._current_span = None

    # ------------------------------------------------------------------
    # character emission
    # ------------------------------------------------------------------
    def write_char(self, ch: str, is_bold: bool, *, count_for_progress: bool = True) -> None:
        """Emit one character to stdout while maintaining cursor + spans.

        ``count_for_progress=False`` is used for synthetic whitespace (line
        breaks inserted between sentences) so the progress bar only tracks
        real document characters.
        """
        out = sys.stdout
        if self._current_span is not None and ch != "\n":
            self._current_span.pieces.append((ch, is_bold))
        if ch == "\n":
            out.write("\n")
            out.flush()
            self._advance_line()
            if count_for_progress:
                self._tick_progress(1)
            # Any active span shouldn't retain a trailing \n segment.
            if self._current_span is not None:
                span = self._current_span
                if span.segments and span.segments[-1].end_col >= span.segments[-1].start_col:
                    span.segments.append(
                        SentenceSegment(abs_row=self.abs_row, start_col=1, end_col=0)
                    )
            return
        w = _char_width(ch)
        if w == 0:
            # Zero-width emitters (e.g. stray BOM) \u2013 write, don't move.
            if is_bold:
                out.write(_ANSI_BOLD_ON + ch + _ANSI_BOLD_OFF)
            else:
                out.write(ch)
            out.flush()
            return
        if self.col + w - 1 > self.content_width:
            # Auto-wrap at the logical cell boundary before the overflow.
            out.write("\n")
            out.flush()
            self._advance_line()
            if self._current_span is not None:
                self._current_span.segments.append(
                    SentenceSegment(abs_row=self.abs_row, start_col=1, end_col=0)
                )
        if is_bold:
            out.write(_ANSI_BOLD_ON + ch + _ANSI_BOLD_OFF)
        else:
            out.write(ch)
        out.flush()
        if self._current_span is not None:
            seg = self._current_span.segments[-1]
            if seg.end_col < seg.start_col:
                seg.start_col = self.col
            seg.end_col = self.col + w - 1
        self.col += w
        if count_for_progress:
            self._tick_progress(1)

    # ------------------------------------------------------------------
    # hover / highlight
    # ------------------------------------------------------------------
    def span_at(self, abs_row: int, col: int) -> SentenceSpan | None:
        for span in self.spans:
            if span.contains(abs_row, col):
                return span
        return None

    def hover(self, span: SentenceSpan | None) -> None:
        if span is self.hovered:
            return
        previously = self.hovered
        self.hovered = span
        if previously is not None and previously is not span:
            self._render_span(previously, self._resting_color(previously))
        if span is not None:
            self._render_span(span, _ANSI_GRAY)
        self._restore_append_cursor()

    def toggle_highlight(self, span: SentenceSpan | None = None) -> None:
        span = span or self.hovered
        if span is None:
            return
        span.highlighted = not span.highlighted
        if span.highlighted:
            self.highlights_order.append(span)
            self._render_span(span, _ANSI_GOLD)
        else:
            if span in self.highlights_order:
                self.highlights_order.remove(span)
            # If mouse is still over it, keep the hover grey; otherwise reset.
            color = _ANSI_GRAY if span is self.hovered else _ANSI_DEFAULT_FG
            self._render_span(span, color)
        self._restore_append_cursor()

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _advance_line(self) -> None:
        self.abs_row += 1
        self.col = 1
        if self.visible_row(self.abs_row) > self.content_height:
            # DEC scrolling region absorbed a newline \u2192 all prior rows
            # shifted up by one. Keep our tracking in sync.
            self.scroll_offset += 1

    def _tick_progress(self, delta: int) -> None:
        self._leaf_reported_chars += delta
        self.done_chars = min(self.done_chars + delta, self.total_chars)
        self.status_bar.update(delta)

    def _resting_color(self, span: SentenceSpan) -> str:
        return _ANSI_GOLD if span.highlighted else _ANSI_DEFAULT_FG

    def _render_span(self, span: SentenceSpan, color: str) -> None:
        """Re-paint ``span`` using the given colour prefix.

        Segments that have scrolled off the visible region are skipped
        silently (hover/click won't ever target them anyway).
        """
        if not span.segments:
            return
        out = sys.stdout
        piece_idx = 0
        for seg in span.segments:
            width = seg.end_col - seg.start_col + 1
            if width <= 0:
                continue
            vis = self.visible_row(seg.abs_row)
            consumed = 0
            if vis < 1 or vis > self.content_height:
                # Still advance piece_idx so the next segment is positioned
                # correctly in the sentence's piece list.
                while piece_idx < len(span.pieces) and consumed < width:
                    ch, _ = span.pieces[piece_idx]
                    w = _char_width(ch)
                    if w == 0:
                        piece_idx += 1
                        continue
                    consumed += w
                    piece_idx += 1
                continue
            out.write(f"\x1b[{vis};{seg.start_col}H")
            out.write(color)
            bold_on = False
            while piece_idx < len(span.pieces) and consumed < width:
                ch, is_bold = span.pieces[piece_idx]
                w = _char_width(ch)
                if w == 0:
                    piece_idx += 1
                    continue
                if is_bold and not bold_on:
                    out.write(_ANSI_BOLD_ON)
                    bold_on = True
                elif not is_bold and bold_on:
                    out.write(_ANSI_BOLD_OFF)
                    bold_on = False
                out.write(ch)
                consumed += w
                piece_idx += 1
            if bold_on:
                out.write(_ANSI_BOLD_OFF)
            out.write(_ANSI_RESET)
        out.flush()

    def _restore_append_cursor(self) -> None:
        vis = self.visible_row(self.abs_row)
        vis = max(1, min(self.content_height, vis))
        sys.stdout.write(f"\x1b[{vis};{self.col}H")
        sys.stdout.flush()


__all__ = [
    "ReadingSession",
    "SentenceSegment",
    "SentenceSpan",
]
