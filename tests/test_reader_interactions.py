"""Unit coverage for the new reader session, mouse parser, and highlights."""
from __future__ import annotations

from pathlib import Path

from youtube_strataread.reader.doc_tree import Node
from youtube_strataread.reader.highlights import write_highlights
from youtube_strataread.reader.mouse import parse as parse_mouse
from youtube_strataread.reader.session import ReadingSession, SentenceSpan
from youtube_strataread.reader.status_bar import NullStatusBar


def test_mouse_parse_move_event():
    # Cb=35 means motion (32) + left button (but button bits zeroed).
    ev = parse_mouse("\x1b[<35;12;5M")
    assert ev is not None
    assert ev.kind == "move"
    assert ev.row == 5
    assert ev.col == 12


def test_mouse_parse_left_click_press():
    ev = parse_mouse("\x1b[<0;20;9M")
    assert ev is not None
    assert ev.kind == "press"
    assert ev.button == 0
    assert ev.row == 9


def test_mouse_parse_left_click_release():
    ev = parse_mouse("\x1b[<0;20;9m")
    assert ev is not None
    assert ev.kind == "release"


def test_mouse_parse_rejects_garbage():
    assert parse_mouse("") is None
    assert parse_mouse("\x1b[A") is None
    assert parse_mouse("hello") is None


def _make_session(tmp_path: Path) -> ReadingSession:
    root = Node(level=0, title="(root)", path="root")
    leaf = Node(
        level=2,
        title="\u5c0f\u8282\u4e00",
        path="1.1",
        body="Hello.",
        sentences=["Hello."],
    )
    root.children.append(leaf)
    session = ReadingSession(
        root=root,
        folder=tmp_path,
        doc_title="demo",
        total_chars=10,
        status_bar=NullStatusBar(),
    )
    session.begin_leaf(leaf, header_rows=0)
    return session


def test_session_write_char_builds_span(tmp_path: Path, capsys):
    session = _make_session(tmp_path)
    session.begin_sentence(0, "Hello.")
    for ch in "Hello.":
        session.write_char(ch, is_bold=False)
    session.write_char("\n", is_bold=False, count_for_progress=False)
    session.end_sentence()
    capsys.readouterr()

    assert len(session.spans) == 1
    span = session.spans[0]
    assert span.text == "Hello."
    assert span.segments
    seg = span.segments[0]
    assert seg.start_col == 1
    # "Hello." is 6 ascii cells, so end_col==6.
    assert seg.end_col == 6
    assert span.contains(seg.abs_row, 3)
    assert not span.contains(seg.abs_row, 99)


def test_highlights_skips_file_when_nothing_highlighted(tmp_path: Path):
    session = _make_session(tmp_path)
    assert write_highlights(session) is None
    assert not (tmp_path / "highlights.md").exists()


def test_highlights_writes_file_when_any(tmp_path: Path):
    session = _make_session(tmp_path)
    span = SentenceSpan(
        leaf_path="1.1",
        leaf_title="\u5c0f\u8282\u4e00",
        sent_idx=0,
        text="\u6211\u559c\u6b22\u8fd9\u53e5\u8bdd\u3002",
        highlighted=True,
    )
    session.highlights_order.append(span)
    path = write_highlights(session)
    assert path == tmp_path / "highlights.md"
    content = path.read_text(encoding="utf-8")
    assert "\u6211\u559c\u6b22\u8fd9\u53e5\u8bdd\u3002" in content
    assert "## \u5c0f\u8282\u4e00" in content
