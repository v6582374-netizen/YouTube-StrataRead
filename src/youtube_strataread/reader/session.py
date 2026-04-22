"""Reader session with bottom-anchored sentence stacking above a sticky footer."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

from youtube_strataread.reader.bionic_render import iter_bionic_chars
from youtube_strataread.reader.doc_tree import Node
from youtube_strataread.reader.status_bar import NullStatusBar, StatusBar

Piece = tuple[str, bool]

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


def _body_blocks(node: Node) -> list[str]:
    if not node.body:
        return []
    return [part for part in node.body.split("\n\n") if part.strip()]


def _line_pieces(text: str, *, bionic: bool) -> list[Piece]:
    return list(iter_bionic_chars(text)) if bionic else [(ch, False) for ch in text]


@dataclass
class HistoryBlock:
    kind: str
    lines: list[list[Piece]] = field(default_factory=list)


@dataclass
class ActiveSentence:
    key: str
    pieces: list[Piece] = field(default_factory=list)
    displayed_chars: int = 0


@dataclass
class RenderLine:
    pieces: list[Piece]
    active: bool = False


@dataclass
class ReadingSession:
    root: Node
    total_chars: int
    status_bar: StatusBar | NullStatusBar

    current_leaf: Node | None = None
    previous_leaf: Node | None = None
    done_chars: int = 0
    _interactive: bool = field(default_factory=_stdout_is_tty, init=False)
    _started: bool = False
    _history_blocks: list[HistoryBlock] = field(default_factory=list)
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
        return max(self.status_bar.content_height, 1)

    @property
    def body_anchor_row(self) -> int:
        return max(self.content_height - 2, 1)

    @property
    def viewport_height(self) -> int:
        return self.body_anchor_row

    def setup(self) -> None:
        self._started = True
        if self._interactive:
            self.render()

    def restore_cursor(self) -> None:
        if not self._interactive or not self._started:
            return
        self.render()

    def breadcrumb_for(self, leaf: Node) -> str:
        titles = [node.title for node in _node_path(self.root, leaf) if node.level > 0 and node.title]
        return " / ".join(titles) or (leaf.title or "(untitled)")

    def begin_leaf(self, leaf: Node) -> None:
        if not self._started:
            self.setup()
        self._settle_active_sentence()
        self.current_leaf = leaf
        self.status_bar.set_context(self.breadcrumb_for(leaf))
        if self._history_blocks:
            self._record_divider()
        for node in self._nodes_to_emit(leaf):
            self._append_node_body(node)
        self.previous_leaf = leaf
        self.status_bar.refresh()
        if self._interactive:
            self.render()

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
        self._settle_active_sentence()
        self._current_sentence = ActiveSentence(key=f"sentence:{self.current_leaf.path}:{sent_idx}")
        del text
        if self._interactive:
            self.render()

    def end_sentence(self) -> None:
        self._settle_active_sentence()
        if self._interactive:
            self.render()
        else:
            self._newline_plain()

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
            run.pieces.append((ch, is_bold))
            if ch == "\n":
                if not self._interactive:
                    self._newline_plain()
                continue
            if not self._interactive:
                self._write_piece(ch, is_bold)
            if count_for_progress:
                self._maybe_tick_sentence_progress(run.key, run.displayed_chars)
            run.displayed_chars += 1
        if self._interactive:
            self.render()

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
        self._record_static_text(text, bionic=bionic)
        self._tick_progress_once(progress_key, len(text))
        if self._interactive:
            self.render()

    def emit_blank_line(self) -> None:
        if not self._started:
            self.setup()
        self._record_blank_line()
        if self._interactive:
            self.render()

    def render(self) -> None:
        if not self._interactive or not self._started:
            return
        layout_changed = self.status_bar.sync()
        if layout_changed:
            self.status_bar.refresh()

        rows = self._collect_render_lines()
        visible = rows[-self.viewport_height :]
        start_row = self.body_anchor_row - len(visible) + 1
        out = sys.stdout
        for row in range(1, self.content_height + 1):
            out.write(f"\x1b[{row};1H")
            out.write(_CLEAR_LINE)
        for offset, line in enumerate(visible):
            out.write(f"\x1b[{start_row + offset};1H")
            self._write_styled_line(out, line)
        out.write(f"\x1b[{self.body_anchor_row};1H")
        out.flush()

    def _nodes_to_emit(self, leaf: Node) -> list[Node]:
        current = [node for node in _node_path(self.root, leaf) if node.level > 0]
        if self.previous_leaf is None:
            return [node for node in current if not node.is_leaf]
        if self.previous_leaf.path == leaf.path:
            return []

        previous = [node for node in _node_path(self.root, self.previous_leaf) if node.level > 0]
        lcp = 0
        while lcp < min(len(previous), len(current)) and previous[lcp].path == current[lcp].path:
            lcp += 1
        return [node for node in current[lcp:] if not node.is_leaf]

    def _append_node_body(self, node: Node) -> None:
        if node.is_leaf or not node.body:
            return
        for block in _body_blocks(node):
            self._record_static_text(block, bionic=block.strip() != "---")
            self._record_blank_line()
        self._tick_progress_once(f"body:{node.path}", len(node.body))

    def _record_static_text(self, text: str, *, bionic: bool) -> None:
        lines = text.split("\n")
        for line in lines:
            if line == "":
                self._record_blank_line()
                continue
            self._history_blocks.append(HistoryBlock(kind="text", lines=[_line_pieces(line, bionic=bionic)]))

        if self._interactive:
            return

        for line in lines:
            if line == "":
                self._newline_plain()
                continue
            for ch, is_bold in _line_pieces(line, bionic=bionic):
                self._write_piece(ch, is_bold)
            self._newline_plain()

    def _record_blank_line(self) -> None:
        self._history_blocks.append(HistoryBlock(kind="blank"))
        if not self._interactive:
            self._newline_plain()

    def _record_divider(self) -> None:
        self._history_blocks.append(HistoryBlock(kind="divider"))
        if not self._interactive:
            sys.stdout.write("─" * self.content_width)
            self._newline_plain()

    def _settle_active_sentence(self) -> None:
        if self._current_sentence is None:
            return
        if self._current_sentence.pieces:
            self._history_blocks.append(
                HistoryBlock(kind="text", lines=[self._current_sentence.pieces.copy()])
            )
        self._current_sentence = None

    def _collect_render_lines(self) -> list[RenderLine]:
        lines: list[RenderLine] = []
        for block in self._history_blocks:
            lines.extend(self._render_lines_for_block(block))
        if self._current_sentence is not None:
            lines.extend(self._wrap_pieces(self._current_sentence.pieces, active=True))
        return lines

    def _render_lines_for_block(self, block: HistoryBlock) -> list[RenderLine]:
        if block.kind == "blank":
            return [RenderLine([])]
        if block.kind == "divider":
            pieces = [("─", False)] * self.content_width
            return [RenderLine(pieces)]

        lines: list[RenderLine] = []
        for raw in block.lines:
            lines.extend(self._wrap_pieces(raw))
        return lines or [RenderLine([])]

    def _wrap_pieces(self, pieces: list[Piece], *, active: bool = False) -> list[RenderLine]:
        if not pieces:
            return [RenderLine([], active=active)]

        lines: list[RenderLine] = []
        current: list[Piece] = []
        current_width = 0
        saw_any = False
        for ch, is_bold in pieces:
            if ch == "\n":
                lines.append(RenderLine(pieces=current, active=active))
                current = []
                current_width = 0
                saw_any = True
                continue
            cell_width = _char_width(ch)
            if cell_width > 0 and current and current_width + cell_width > self.content_width:
                lines.append(RenderLine(pieces=current, active=active))
                current = []
                current_width = 0
            current.append((ch, is_bold))
            current_width += cell_width
            saw_any = True
        if current or not saw_any:
            lines.append(RenderLine(pieces=current, active=active))
        return lines

    def _maybe_tick_sentence_progress(self, key: str, displayed_chars: int) -> None:
        seen = self._seen_sentence_chars.get(key, 0)
        if displayed_chars < seen:
            return
        self._seen_sentence_chars[key] = seen + 1
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

    @staticmethod
    def _write_styled_line(out, line: RenderLine) -> None:
        if not line.pieces:
            return
        out.write(_ANSI_GOLD if line.active else _ANSI_DEFAULT_FG)
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

    @staticmethod
    def _write_piece(ch: str, is_bold: bool) -> None:
        if is_bold:
            sys.stdout.write(_ANSI_BOLD_ON + ch + _ANSI_BOLD_OFF)
        else:
            sys.stdout.write(ch)
        sys.stdout.flush()

    @staticmethod
    def _newline_plain() -> None:
        sys.stdout.write("\n")
        sys.stdout.flush()


__all__ = ["ReadingSession", "RenderLine"]
