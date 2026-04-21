"""Mode A: manual Tab-to-advance sentence reader."""
from __future__ import annotations

import time

from rich.console import Console

from youtube_strataread.reader.bionic_render import iter_bionic_chars
from youtube_strataread.reader.doc_tree import Node
from youtube_strataread.reader.keys import Key, key_reader
from youtube_strataread.reader.session import ReadingSession

CHAR_TYPE_DELAY = 0.012


def read_leaf_manual(leaf: Node, console: Console, session: ReadingSession) -> str:
    """Blocking loop. Returns the exit reason ('done' | 'back' | 'quit')."""
    del console
    session.begin_leaf(leaf)

    sentences = leaf.sentences or ([leaf.body] if leaf.body else [])
    if not sentences:
        session.emit_static_text("（本小节暂无正文。按 Esc 返回。）")
        return _wait_for_back()

    idx = 0
    max_seen_idx = 0
    _show_sentence(session, sentences[idx], idx, animate=True, count_for_progress=True)

    with key_reader() as read:
        while True:
            key = read()
            if key is None:
                continue
            action = _classify(key)
            if action == "quit":
                session.finish_leaf(completed=False)
                return "quit"
            if action == "back":
                session.finish_leaf(completed=False)
                return "back"
            if action == "next":
                if idx + 1 >= len(sentences):
                    session.finish_leaf(completed=True)
                    return "done"
                idx += 1
                if idx > max_seen_idx:
                    _show_sentence(session, sentences[idx], idx, animate=True, count_for_progress=True)
                    max_seen_idx = idx
                else:
                    _show_sentence(session, sentences[idx], idx, animate=False, count_for_progress=False)
            elif action == "prev":
                if idx == 0:
                    continue
                idx -= 1
                _show_sentence(session, sentences[idx], idx, animate=False, count_for_progress=False)
            elif action == "jump_end":
                if idx + 1 >= len(sentences):
                    continue
                while idx + 1 < len(sentences):
                    idx += 1
                    count_for_progress = idx > max_seen_idx
                    _show_sentence(
                        session,
                        sentences[idx],
                        idx,
                        animate=False,
                        count_for_progress=count_for_progress,
                    )
                    max_seen_idx = max(max_seen_idx, idx)


def _show_sentence(
    session: ReadingSession,
    sentence: str,
    sent_idx: int,
    *,
    animate: bool,
    count_for_progress: bool,
) -> None:
    session.begin_sentence(sent_idx, sentence)
    pieces = list(iter_bionic_chars(sentence))
    if animate:
        for ch, is_bold in pieces:
            session.write_char(ch, is_bold, count_for_progress=count_for_progress)
            time.sleep(CHAR_TYPE_DELAY)
    else:
        session.write_chars(pieces, count_for_progress=count_for_progress)
    session.end_sentence()


def _classify(key: Key) -> str:
    k = key.key
    if k in ("q", "ctrl-c"):
        return "quit"
    if k in ("escape", "b"):
        return "back"
    if k == "tab":
        return "next"
    if k == "shift-tab":
        return "prev"
    if k == "space":
        return "jump_end"
    return "noop"


def _wait_for_back() -> str:
    with key_reader() as read:
        while True:
            k = read()
            if k is None:
                continue
            if k.key in ("escape", "b", "q", "ctrl-c"):
                return "back" if k.key != "q" else "quit"
