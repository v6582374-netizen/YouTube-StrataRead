"""Unit coverage for the bottom-anchored reader session layout."""
from __future__ import annotations

from youtube_strataread.reader.doc_tree import Node
from youtube_strataread.reader.session import ReadingSession


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


def _make_tree() -> tuple[Node, Node]:
    root = Node(level=0, title="(root)", path="root")
    chapter = Node(level=1, title="Part", path="1")
    section = Node(level=2, title="Section", path="1.1")
    leaf = Node(
        level=3,
        title="Leaf",
        path="1.1.1",
        body="alpha beta gamma",
        sentences=["alpha", "beta", "gamma"],
    )
    section.children.append(leaf)
    chapter.children.append(section)
    root.children.append(chapter)
    return root, leaf


def _make_session(*, width: int = 20, content_height: int = 4) -> tuple[ReadingSession, DummyStatusBar]:
    root, leaf = _make_tree()
    bar = DummyStatusBar(width=width, content_height=content_height)
    session = ReadingSession(root=root, total_chars=100, status_bar=bar)
    session.begin_leaf(leaf)
    return session, bar


def _show_sentence(
    session: ReadingSession,
    text: str,
    sent_idx: int,
    *,
    count_for_progress: bool = False,
) -> None:
    session.begin_sentence(sent_idx, text)
    session.write_chars([(ch, False) for ch in text], count_for_progress=count_for_progress)
    session.end_sentence()


def test_session_sets_footer_breadcrumb_to_full_path() -> None:
    _, bar = _make_session()
    assert bar.context == "Part / Section / Leaf"


def test_visible_lines_keep_current_sentence_at_bottom() -> None:
    session, _ = _make_session()
    _show_sentence(session, "Older", 0)
    _show_sentence(session, "Current", 1)

    lines = session._visible_lines()

    assert [line.text for line in lines] == ["Older", "Current"]
    assert lines[0].active is False
    assert lines[-1].active is True


def test_visible_lines_drop_oldest_rows_when_content_overflows() -> None:
    session, _ = _make_session(content_height=3)
    _show_sentence(session, "one", 0)
    _show_sentence(session, "two", 1)
    _show_sentence(session, "three", 2)
    _show_sentence(session, "four", 3)

    lines = session._visible_lines()

    assert [line.text for line in lines] == ["two", "three", "four"]
    assert lines[-1].active is True


def test_wrapped_current_sentence_stays_on_bottom_rows() -> None:
    session, _ = _make_session(width=10, content_height=3)
    _show_sentence(session, "older", 0)
    _show_sentence(session, "abcdefghijklm", 1)

    lines = session._visible_lines()

    assert [line.text for line in lines] == ["older", "abcdefghij", "klm"]
    assert lines[0].active is False
    assert lines[1].active is True
    assert lines[2].active is True


def test_rebuild_without_progress_does_not_double_count_chars() -> None:
    session, bar = _make_session()
    _show_sentence(session, "alpha", 0, count_for_progress=True)
    before = (session.done_chars, bar.done_chars)

    session.reset_view()
    _show_sentence(session, "alpha", 0, count_for_progress=False)

    assert (session.done_chars, bar.done_chars) == before
