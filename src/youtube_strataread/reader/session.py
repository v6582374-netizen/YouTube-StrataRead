"""Append-only reading session with bottom-anchored streaming output."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

from youtube_strataread.reader.bionic_render import iter_bionic_chars
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


def _node_path(root: Node, target: Node) -> list[Node]:
    path: list[Node] = []

    def dfs(node: Node) -> bool:
        if node is target:
            path.append(node)
            return True
        for child in node.children:
            if dfs(child):
                path.append(node)
                return True
        return False

    if dfs(root):
        return list(reversed(path))
    return [target]


def _heading_text(node: Node) -> str:
    hashes = "#" * max(node.level, 1)
    return f"{hashes} {node.title}".rstrip()


def _body_blocks(node: Node) -> list[str]:
    if not node.body:
        return []
    return [part for part in node.body.split("\n\n") if part.strip()]


@dataclass
class RunSegment:
    abs_row: int
    start_col: int
    end_col: int


@dataclass
class ActiveSentence:
    key: str
    pieces: list[tuple[str, bool]] = field(default_factory=list)
    segments: list[RunSegment] = field(default_factory=list)
    displayed_chars: int = 0


@dataclass
class ReadingSession:
    root: Node
    total_chars: int
    status_bar: StatusBar | NullStatusBar

    current_leaf: Node | None = None
    previous_leaf: Node | None = None
    done_chars: int = 0
    abs_row: int = 0
    col: int = 1
    scroll_offset: int = 0
    _interactive: bool = field(default_factory=_stdout_is_tty, init=False)
    _started: bool = False
    _current_sentence: ActiveSentence | None = None
    _seen_block_keys: set[str] = field(default_factory=set)
    _seen_sentence_chars: dict[str, int] = field(default_factory=dict)
    _leaf_progress_chars: dict[str, int] = field(default_factory=dict)
    _completed_leafs: set[str] = field(default_factory=set)

    @property
    def content_width(self) -> int:
        return max(self.status_bar.width, 10)

    @property
    def content_height(self) -> int:
        return max(self.status_bar.content_height, 3)

    def setup(self) -> None:
        self.abs_row = self.content_height
        self.col = 1
        self.scroll_offset = 0
        self._started = True
        if not self._interactive:
            return
        out = sys.stdout
        for row in range(1, self.content_height + 1):
            out.write(f"\x1b[{row};1H")
            out.write(_CLEAR_LINE)
        out.write(f"\x1b[{self.content_height};1H")
        out.flush()

    def restore_cursor(self) -> None:
        if not self._interactive or not self._started:
            return
        vis = max(1, min(self.content_height, self.visible_row(self.abs_row)))
        sys.stdout.write(f"\x1b[{vis};{self.col}H")
        sys.stdout.flush()

    def visible_row(self, abs_row: int) -> int:
        return abs_row - self.scroll_offset

    def breadcrumb_for(self, leaf: Node) -> str:
        titles = [node.title for node in _node_path(self.root, leaf) if node.level > 0 and node.title]
        return " / ".join(titles) or (leaf.title or "(untitled)")

    def begin_leaf(self, leaf: Node) -> None:
        if not self._started:
            self.setup()
        self._close_active_sentence()
        self.current_leaf = leaf
        self.status_bar.set_context(self.breadcrumb_for(leaf))
        for node in self._nodes_to_emit(leaf):
            self._emit_node(node)
        self.previous_leaf = leaf
        self.status_bar.refresh()

    def finish_leaf(self, *, completed: bool) -> None:
        if not completed or self.current_leaf is None:
            return
        path = self.current_leaf.path
        if path in self._completed_leafs:
            return
        seen = self._leaf_progress_chars.get(path, 0)
        total = len(self.current_leaf.body or "")
        if seen < total:
            delta = total - seen
            self._tick_progress(delta)
            self._leaf_progress_chars[path] = total
        self._completed_leafs.add(path)

    def begin_sentence(self, sent_idx: int, text: str) -> None:
        if self.current_leaf is None:
            raise RuntimeError("begin_leaf must run first")
        if not self._started:
            self.setup()
        self._close_active_sentence()
        key = f"sentence:{self.current_leaf.path}:{sent_idx}"
        self._current_sentence = ActiveSentence(
            key=key,
            segments=[RunSegment(abs_row=self.abs_row, start_col=self.col, end_col=self.col - 1)],
        )
        del text

    def end_sentence(self) -> None:
        if self._current_sentence is None:
            return
        run = self._current_sentence
        if run.segments and run.segments[-1].end_col < run.segments[-1].start_col:
            run.segments.pop()

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
        run = self._current_sentence
        for ch, is_bold in pieces:
            if ch == "\n":
                continue
            self._write_piece(ch, is_bold, color=_ANSI_GOLD, track_current=True)
            run.pieces.append((ch, is_bold))
            if count_for_progress:
                self._maybe_tick_sentence_progress(run)
            run.displayed_chars += 1

    def emit_static_text(
        self,
        text: str,
        *,
        bionic: bool = False,
        progress_key: str | None = None,
    ) -> None:
        if not text:
            self.emit_blank_line()
            return
        lines = text.split("\n")
        for line in lines:
            if line == "":
                self.emit_blank_line()
                continue
            if self.col != 1:
                self._newline(track_current=False)
            pieces = list(iter_bionic_chars(line)) if bionic else [(ch, False) for ch in line]
            for ch, is_bold in pieces:
                self._write_piece(ch, is_bold, color=_ANSI_DEFAULT_FG, track_current=False)
            self._newline(track_current=False)
        self._tick_progress_once(progress_key, len(text))

    def emit_blank_line(self) -> None:
        if not self._started:
            self.setup()
        if self.col != 1:
            self._newline(track_current=False)
        self._newline(track_current=False)

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _nodes_to_emit(self, leaf: Node) -> list[Node]:
        current = [node for node in _node_path(self.root, leaf) if node.level > 0]
        if self.previous_leaf is None or self.previous_leaf.path == leaf.path:
            return current
        previous = [node for node in _node_path(self.root, self.previous_leaf) if node.level > 0]
        lcp = 0
        while lcp < min(len(previous), len(current)) and previous[lcp].path == current[lcp].path:
            lcp += 1
        return current[lcp:]

    def _emit_node(self, node: Node) -> None:
        self.emit_static_text(_heading_text(node), progress_key=f"heading:{node.path}")
        self.emit_blank_line()
        if node.is_leaf:
            return
        for block in _body_blocks(node):
            self.emit_static_text(
                block,
                bionic=block.strip() != "---",
            )
            self.emit_blank_line()
        self._tick_progress_once(f"body:{node.path}", len(node.body))

    def _close_active_sentence(self) -> None:
        if self._current_sentence is None:
            return
        self._render_run(self._current_sentence, _ANSI_DEFAULT_FG)
        self._current_sentence = None
        self._newline(track_current=False)

    def _maybe_tick_sentence_progress(self, run: ActiveSentence) -> None:
        seen = self._seen_sentence_chars.get(run.key, 0)
        if run.displayed_chars < seen:
            return
        self._seen_sentence_chars[run.key] = seen + 1
        self._tick_progress(1)
        if self.current_leaf is not None:
            path = self.current_leaf.path
            self._leaf_progress_chars[path] = self._leaf_progress_chars.get(path, 0) + 1

    def _tick_progress_once(self, key: str | None, amount: int) -> None:
        if not key or amount <= 0 or key in self._seen_block_keys:
            return
        self._seen_block_keys.add(key)
        self._tick_progress(amount)

    def _tick_progress(self, delta: int) -> None:
        if delta <= 0:
            return
        self.done_chars = min(self.done_chars + delta, self.total_chars)
        self.status_bar.update(delta)

    def _newline(self, *, track_current: bool) -> None:
        if self._interactive:
            sys.stdout.write("\n")
            sys.stdout.flush()
        else:
            sys.stdout.write("\n")
        self.abs_row += 1
        self.col = 1
        if self.visible_row(self.abs_row) > self.content_height:
            self.scroll_offset += 1
        if track_current and self._current_sentence is not None:
            self._current_sentence.segments.append(
                RunSegment(abs_row=self.abs_row, start_col=1, end_col=0)
            )

    def _write_piece(self, ch: str, is_bold: bool, *, color: str, track_current: bool) -> None:
        w = _char_width(ch)
        if w > 0 and self.col + w - 1 > self.content_width:
            self._newline(track_current=track_current)
        if self._interactive:
            sys.stdout.write(color)
        if is_bold:
            sys.stdout.write(_ANSI_BOLD_ON + ch + _ANSI_BOLD_OFF)
        else:
            sys.stdout.write(ch)
        if self._interactive:
            sys.stdout.write(_ANSI_RESET)
        sys.stdout.flush()
        if track_current and self._current_sentence is not None and w > 0:
            seg = self._current_sentence.segments[-1]
            if seg.end_col < seg.start_col:
                seg.start_col = self.col
            seg.end_col = self.col + w - 1
        self.col += w

    def _render_run(self, run: ActiveSentence, color: str) -> None:
        if not self._interactive or not run.segments:
            return
        out = sys.stdout
        piece_idx = 0
        for seg in run.segments:
            width = seg.end_col - seg.start_col + 1
            if width <= 0:
                continue
            visible = self.visible_row(seg.abs_row)
            consumed = 0
            if visible < 1 or visible > self.content_height:
                while piece_idx < len(run.pieces) and consumed < width:
                    ch, _ = run.pieces[piece_idx]
                    piece_idx += 1
                    consumed += _char_width(ch)
                continue
            out.write(f"\x1b[{visible};{seg.start_col}H")
            out.write(color)
            bold_on = False
            while piece_idx < len(run.pieces) and consumed < width:
                ch, is_bold = run.pieces[piece_idx]
                piece_idx += 1
                char_width = _char_width(ch)
                if char_width == 0:
                    continue
                if is_bold and not bold_on:
                    out.write(_ANSI_BOLD_ON)
                    bold_on = True
                elif not is_bold and bold_on:
                    out.write(_ANSI_BOLD_OFF)
                    bold_on = False
                out.write(ch)
                consumed += char_width
            if bold_on:
                out.write(_ANSI_BOLD_OFF)
            out.write(_ANSI_RESET)
        out.flush()
        self.restore_cursor()


__all__ = ["ReadingSession"]
