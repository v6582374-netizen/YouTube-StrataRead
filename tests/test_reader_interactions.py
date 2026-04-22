"""Unit coverage for the append-only reader session and footer geometry."""
from __future__ import annotations

import io
import re
import sys

import pyte

from youtube_strataread.reader.doc_tree import Node
from youtube_strataread.reader.session import ReadingSession
from youtube_strataread.reader.status_bar import StatusBar

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b7|\x1b8")


class DummyStatusBar:
    def __init__(self, *, width: int = 20, content_height: int = 4) -> None:
        self.width = width
        self.content_height = content_height
        self.context = ""
        self.done_chars = 0

    def setup(self) -> None:
        return

    def teardown(self) -> None:
        return

    def update(self, delta_chars: int) -> None:
        self.done_chars += delta_chars

    def set_progress(self, done_chars: int) -> None:
        self.done_chars = done_chars

    def refresh(self) -> None:
        return

    def set_context(self, text: str) -> None:
        self.context = text


class TTYBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True

    def flush(self) -> None:
        return


def _strip_ansi(text: str) -> str:
    plain = _ANSI_RE.sub("", text)
    return plain.replace("\r\n", "\n").replace("\r", "\n")


def _make_tree() -> tuple[Node, Node, Node]:
    root = Node(level=0, title="(root)", path="root")
    chapter = Node(level=1, title="Part", path="1", body="Chapter intro.")
    section = Node(level=2, title="Section", path="1.1", body="Section intro.")
    leaf_a = Node(
        level=3,
        title="Leaf A",
        path="1.1.1",
        body="Alpha. Beta.",
        sentences=["Alpha.", "Beta."],
    )
    leaf_b = Node(
        level=3,
        title="Leaf B",
        path="1.1.2",
        body="Gamma.",
        sentences=["Gamma."],
    )
    section.children.extend([leaf_a, leaf_b])
    chapter.children.append(section)
    root.children.append(chapter)
    return root, leaf_a, leaf_b


def _make_compact_tree() -> tuple[Node, Node]:
    root = Node(level=0, title="(root)", path="root")
    chapter = Node(level=1, title="Part", path="1", body="Intro.")
    leaf = Node(
        level=2,
        title="Leaf",
        path="1.1",
        body="Alpha. Beta.",
        sentences=["Alpha.", "Beta."],
    )
    chapter.children.append(leaf)
    root.children.append(chapter)
    return root, leaf


def _make_session(*, width: int = 20, content_height: int = 4) -> tuple[ReadingSession, DummyStatusBar, Node, Node]:
    root, leaf_a, leaf_b = _make_tree()
    bar = DummyStatusBar(width=width, content_height=content_height)
    session = ReadingSession(root=root, total_chars=500, status_bar=bar)
    session.setup()
    return session, bar, leaf_a, leaf_b


def _make_interactive_capture(monkeypatch, *, width: int = 20, height: int = 10):
    monkeypatch.setattr(StatusBar, "_detect_tty", staticmethod(lambda: True))
    monkeypatch.setattr(StatusBar, "_detect_size", staticmethod(lambda: (width, height)))

    buffer = TTYBuffer()
    monkeypatch.setattr(sys, "stdout", buffer)

    root, leaf = _make_compact_tree()
    bar = StatusBar(total_chars=200, contexts=["Part / Leaf"])
    session = ReadingSession(root=root, total_chars=200, status_bar=bar)
    bar.setup()
    session.setup()
    return session, leaf, buffer


def _screen_from_output(output: str, *, width: int, height: int) -> pyte.Screen:
    screen = pyte.Screen(width, height)
    stream = pyte.Stream()
    stream.attach(screen)
    stream.feed(output)
    return screen


def _show_sentence(
    session: ReadingSession,
    text: str,
    sent_idx: int,
    *,
    count_for_progress: bool = True,
) -> None:
    session.begin_sentence(sent_idx, text)
    session.write_chars([(ch, False) for ch in text], count_for_progress=count_for_progress)
    session.end_sentence()


def test_session_sets_footer_breadcrumb_to_full_path(capsys) -> None:
    session, bar, leaf_a, _ = _make_session()
    session.begin_leaf(leaf_a)
    capsys.readouterr()
    assert bar.context == "Part / Section / Leaf A"


def test_begin_leaf_appends_markdown_headings_and_preserves_history(capsys) -> None:
    session, _, leaf_a, leaf_b = _make_session()

    session.begin_leaf(leaf_a)
    _show_sentence(session, "Alpha.", 0)
    session.begin_leaf(leaf_b)
    _show_sentence(session, "Gamma.", 0)

    output = _strip_ansi(capsys.readouterr().out)

    assert "# Part" in output
    assert "## Section" in output
    assert "### Leaf A" in output
    assert "### Leaf B" in output
    assert output.count("# Part") == 1
    assert output.count("## Section") == 1
    assert output.index("Alpha.") < output.index("### Leaf B")


def test_non_leaf_body_progress_counts_full_multiblock_text_once(capsys) -> None:
    root = Node(level=0, title="(root)", path="root")
    chapter = Node(level=1, title="Part", path="1", body="Intro.\n\n---\n\nAfter.")
    leaf = Node(level=2, title="Leaf", path="1.1", body="Body.", sentences=["Body."])
    chapter.children.append(leaf)
    root.children.append(chapter)
    bar = DummyStatusBar(width=30, content_height=5)
    session = ReadingSession(root=root, total_chars=200, status_bar=bar)

    session.setup()
    session.begin_leaf(leaf)

    output = _strip_ansi(capsys.readouterr().out)

    expected = len("# Part") + len(chapter.body) + len("## Leaf")
    assert session.done_chars == expected
    assert "---" in output


def test_reenter_same_leaf_reprints_full_path_context(capsys) -> None:
    session, _, leaf_a, _ = _make_session()

    session.begin_leaf(leaf_a)
    _show_sentence(session, "Alpha.", 0)
    session.begin_leaf(leaf_a)
    _show_sentence(session, "Alpha.", 0, count_for_progress=False)

    output = _strip_ansi(capsys.readouterr().out)

    assert output.count("# Part") == 2
    assert output.count("## Section") == 2
    assert output.count("### Leaf A") == 2


def test_partial_leaf_does_not_top_up_progress_until_completed(capsys) -> None:
    session, bar, leaf_a, _ = _make_session()

    session.begin_leaf(leaf_a)
    before_sentence = session.done_chars
    _show_sentence(session, leaf_a.sentences[0], 0, count_for_progress=True)
    after_first_sentence = session.done_chars
    session.finish_leaf(completed=False)
    after_partial_finish = session.done_chars

    session.begin_leaf(leaf_a)
    _show_sentence(session, leaf_a.sentences[1], 1, count_for_progress=True)
    session.finish_leaf(completed=True)
    capsys.readouterr()

    assert after_first_sentence - before_sentence == len("Alpha.")
    assert after_partial_finish == after_first_sentence
    assert session.done_chars - before_sentence == len(leaf_a.body)
    assert bar.done_chars == session.done_chars


def test_status_bar_reserves_three_footer_rows(monkeypatch) -> None:
    monkeypatch.setattr(StatusBar, "_detect_tty", staticmethod(lambda: True))
    monkeypatch.setattr(StatusBar, "_detect_size", staticmethod(lambda: (80, 24)))

    bar = StatusBar(total_chars=100)

    assert bar.content_height == 21


def test_status_bar_progress_line_never_overflows_narrow_width(monkeypatch) -> None:
    monkeypatch.setattr(StatusBar, "_detect_tty", staticmethod(lambda: True))
    monkeypatch.setattr(StatusBar, "_detect_size", staticmethod(lambda: (8, 24)))

    bar = StatusBar(total_chars=100)
    bar.done_chars = 42

    line = _strip_ansi(bar._progress_line())

    assert len(line) <= bar.width


def test_status_bar_uses_classic_progress_bar_style(monkeypatch) -> None:
    monkeypatch.setattr(StatusBar, "_detect_tty", staticmethod(lambda: True))
    monkeypatch.setattr(StatusBar, "_detect_size", staticmethod(lambda: (30, 24)))

    bar = StatusBar(total_chars=100)
    bar.done_chars = 42

    line = _strip_ansi(bar._progress_line())

    assert line.startswith("[")
    assert "]" in line
    assert "%" in line
    assert "░" in line


def test_status_bar_wraps_breadcrumb_instead_of_truncating(monkeypatch) -> None:
    monkeypatch.setattr(StatusBar, "_detect_tty", staticmethod(lambda: True))
    monkeypatch.setattr(StatusBar, "_detect_size", staticmethod(lambda: (12, 24)))

    bar = StatusBar(total_chars=100)
    bar.set_context("Parent / Current / ExtremelyLongLeafTitle")

    assert len(bar._context_lines) > 1
    assert "..." not in "".join(bar._context_lines)


def test_status_bar_keeps_content_height_stable_across_chapter_context_switches(monkeypatch) -> None:
    monkeypatch.setattr(StatusBar, "_detect_tty", staticmethod(lambda: True))
    monkeypatch.setattr(StatusBar, "_detect_size", staticmethod(lambda: (18, 24)))

    contexts = [
        "Part / Short",
        "Part / Section / Extremely Long Leaf Title That Must Wrap",
    ]
    bar = StatusBar(total_chars=100, contexts=contexts)

    baseline = bar.content_height
    bar.set_context(contexts[0])
    first = bar.content_height
    bar.set_context(contexts[1])
    second = bar.content_height

    assert baseline == first == second
    assert bar._reserved_context_rows >= len(bar._context_lines)


def test_interactive_session_setup_starts_at_top_left(monkeypatch) -> None:
    _, _, buffer = _make_interactive_capture(monkeypatch, width=20, height=10)

    screen = _screen_from_output(buffer.getvalue(), width=20, height=10)

    assert (screen.cursor.y, screen.cursor.x) == (0, 0)


def test_interactive_session_newlines_return_to_first_column(monkeypatch) -> None:
    session, leaf, buffer = _make_interactive_capture(monkeypatch, width=20, height=10)

    session.begin_leaf(leaf)
    _show_sentence(session, "Alpha.", 0)

    screen = _screen_from_output(buffer.getvalue(), width=20, height=10)

    assert any(row.startswith("Alpha.") for row in screen.display[:-2])


def test_interactive_session_keeps_footer_rows_separate_from_body(monkeypatch) -> None:
    session, leaf, buffer = _make_interactive_capture(monkeypatch, width=20, height=10)

    session.begin_leaf(leaf)
    _show_sentence(session, "Alpha.", 0)

    screen = _screen_from_output(buffer.getvalue(), width=20, height=10)

    assert screen.display[-2].startswith("Part / Leaf")
    assert screen.display[-1].startswith("[")
    assert all("Part / Leaf" not in row for row in screen.display[:-2])
    assert all("Alpha." not in row for row in screen.display[-2:])


def test_interactive_session_does_not_reposition_cursor_while_appending(capsys) -> None:
    session, _, leaf_a, _ = _make_session(width=12, content_height=4)
    session._interactive = True
    session.setup()
    capsys.readouterr()

    session.begin_leaf(leaf_a)
    _show_sentence(session, "ABCDEFGHIJKL", 0)
    _show_sentence(session, "Beta.", 1)

    output = capsys.readouterr().out

    assert re.search(r"\x1b\[\d+;\d+H", output) is None
    assert output.index("ABCDEFGHIJKL") < output.index("Beta.")
