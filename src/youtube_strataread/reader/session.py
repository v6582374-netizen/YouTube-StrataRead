"""Shared state for the bottom-anchored interactive reader.

The session owns three concerns shared by both reading modes:

1. Whole-document progress reporting via :class:`StatusBar`.
2. Bottom-anchored sentence layout where the active sentence always hugs the
   footer and older sentences are pushed upward.
3. Terminal redraws for the content area, while the footer stays sticky.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

from youtube_strataread.reader.doc_tree import Node
from youtube_strataread.reader.status_bar import NullStatusBar, StatusBar

_ANSI_RESET = "\x1b[0m"
_ANSI_BOLD_ON = "\x1b[1m"
_ANSI_BOLD_OFF = "\x1b[22m"
_ANSI_DEFAULT_FG = "\x1b[39m"
_ANSI_GOLD = "\x1b[38;2;247;231;172m"
_CLEAR_LINE = "\x1b[2K"


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


def _stdout_is_tty() -> bool:
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _titles_to_target(root: Node, target: Node) -> list[str]:
    path: list[str] = []

    def dfs(node: Node) -> bool:
        if node is target:
            return True
        for child in node.children:
            if dfs(child):
                if child.title:
                    path.append(child.title)
                return True
        return False

    if dfs(root):
        return list(reversed(path))
    return [target.title] if target.title else []


@dataclass
class SentenceView:
    sent_idx: int
    text: str
    pieces: list[tuple[str, bool]] = field(default_factory=list)
    finished: bool = False


@dataclass
class RenderedLine:
    pieces: list[tuple[str, bool]]
    active: bool = False

    @property
    def text(self) -> str:
        return "".join(ch for ch, _ in self.pieces)


@dataclass
class ReadingSession:
    root: Node
    total_chars: int
    status_bar: StatusBar | NullStatusBar

    current_leaf: Node | None = None
    completed_sentences: list[SentenceView] = field(default_factory=list)
    _current_sentence: SentenceView | None = None
    done_chars: int = 0
    _leaf_reported_chars: int = 0
    _interactive: bool = field(default_factory=_stdout_is_tty, init=False)

    @property
    def content_width(self) -> int:
        return max(self.status_bar.width, 10)

    @property
    def content_height(self) -> int:
        return max(self.status_bar.content_height, 3)

    def begin_leaf(self, leaf: Node) -> None:
        self.current_leaf = leaf
        self._leaf_reported_chars = 0
        self.status_bar.set_context(self.breadcrumb_for(leaf))
        self.reset_view()
        self.status_bar.refresh()

    def breadcrumb_for(self, leaf: Node) -> str:
        titles = _titles_to_target(self.root, leaf)
        return " / ".join(titles) or (leaf.title or "(untitled)")

    def finish_leaf(self) -> None:
        if self.current_leaf is None:
            return
        total = len(self.current_leaf.body or "")
        if self._leaf_reported_chars < total:
            delta = total - self._leaf_reported_chars
            self.done_chars = min(self.done_chars + delta, self.total_chars)
            self.status_bar.update(delta)
            self._leaf_reported_chars = total

    def reset_view(self) -> None:
        self.completed_sentences = []
        self._current_sentence = None
        self.render()

    def begin_sentence(self, sent_idx: int, text: str) -> None:
        if self._current_sentence is not None:
            self.completed_sentences.append(self._current_sentence)
        self._current_sentence = SentenceView(sent_idx=sent_idx, text=text)
        self.render()

    def end_sentence(self) -> None:
        if self._current_sentence is None:
            return
        self._current_sentence.finished = True
        self.render()

    def write_char(self, ch: str, is_bold: bool, *, count_for_progress: bool = True) -> None:
        self.write_chars([(ch, is_bold)], count_for_progress=count_for_progress)

    def write_chars(
        self,
        pieces: list[tuple[str, bool]],
        *,
        count_for_progress: bool = True,
    ) -> None:
        if self._current_sentence is None:
            raise RuntimeError("begin_sentence must run before write_chars")
        delta = 0
        for ch, is_bold in pieces:
            if ch == "\n":
                continue
            self._current_sentence.pieces.append((ch, is_bold))
            delta += 1
            if not self._interactive and count_for_progress:
                self._write_plain(ch, is_bold)
        if count_for_progress and delta > 0:
            self._tick_progress(delta)
        if self._interactive:
            self.render()

    def render(self) -> None:
        if not self._interactive:
            return
        rows = self._visible_lines()
        start_row = self.content_height - len(rows) + 1
        out = sys.stdout
        for row in range(1, self.content_height + 1):
            out.write(f"\x1b[{row};1H")
            out.write(_CLEAR_LINE)
        for offset, line in enumerate(rows):
            out.write(f"\x1b[{start_row + offset};1H")
            self._write_styled_line(out, line)
        out.write(f"\x1b[{self.content_height};1H")
        out.flush()

    def _visible_lines(self) -> list[RenderedLine]:
        lines: list[RenderedLine] = []
        for sentence in self.completed_sentences:
            lines.extend(self._wrap_sentence(sentence, active=False))
        if self._current_sentence is not None:
            lines.extend(self._wrap_sentence(self._current_sentence, active=True))
        if len(lines) <= self.content_height:
            return lines
        return lines[-self.content_height :]

    def _wrap_sentence(self, sentence: SentenceView, *, active: bool) -> list[RenderedLine]:
        if not sentence.pieces:
            return []
        rows: list[RenderedLine] = []
        current: list[tuple[str, bool]] = []
        width = 0
        for ch, is_bold in sentence.pieces:
            cell_width = _char_width(ch)
            if cell_width == 0:
                current.append((ch, is_bold))
                continue
            if current and width + cell_width > self.content_width:
                rows.append(RenderedLine(pieces=current, active=active))
                current = []
                width = 0
            current.append((ch, is_bold))
            width += cell_width
        if current:
            rows.append(RenderedLine(pieces=current, active=active))
        return rows

    def _tick_progress(self, delta: int) -> None:
        self._leaf_reported_chars += delta
        self.done_chars = min(self.done_chars + delta, self.total_chars)
        self.status_bar.update(delta)

    def _write_plain(self, ch: str, is_bold: bool) -> None:
        if is_bold:
            sys.stdout.write(_ANSI_BOLD_ON + ch + _ANSI_BOLD_OFF)
        else:
            sys.stdout.write(ch)
        sys.stdout.flush()

    def _write_styled_line(self, out, line: RenderedLine) -> None:
        color = _ANSI_GOLD if line.active else _ANSI_DEFAULT_FG
        out.write(color)
        bold_on = False
        for ch, is_bold in line.pieces:
            if is_bold and not bold_on:
                out.write(_ANSI_BOLD_ON)
                bold_on = True
            elif not is_bold and bold_on:
                out.write(_ANSI_BOLD_OFF)
                bold_on = False
            out.write(ch)
        if bold_on:
            out.write(_ANSI_BOLD_OFF)
        out.write(_ANSI_RESET)


__all__ = ["ReadingSession", "RenderedLine"]
