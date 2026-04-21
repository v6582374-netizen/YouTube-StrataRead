"""Mode A: manual Tab-to-advance sentence reader.

Given a leaf :class:`Node`, this loop:
- prints the leaf's title
- each Tab press reveals the next sentence (typed out character-by-character)
- Shift+Tab shows the previous sentence (re-typed instantly)
- Space skips to the last sentence
- ``h``            toggles highlight on the hovered sentence (keyboard fallback)
- mouse move      hovers a sentence (turns grey)
- mouse click     toggles champagne-gold highlight on the hovered sentence
- Esc / b / q     returns control to the caller
"""
from __future__ import annotations

import time

from rich.console import Console

from youtube_strataread.reader.bionic_render import iter_bionic_chars
from youtube_strataread.reader.doc_tree import Node
from youtube_strataread.reader.keys import Key, key_reader
from youtube_strataread.reader.mouse import parse as parse_mouse
from youtube_strataread.reader.session import ReadingSession

# Slightly brisker than before per user request (~1.65x faster than 0.02s).
CHAR_TYPE_DELAY = 0.012


def read_leaf_manual(leaf: Node, console: Console, session: ReadingSession) -> str:
    """Blocking loop. Returns the *exit reason* ('done' | 'back' | 'quit')."""
    _render_header(console, leaf)
    session.begin_leaf(leaf, header_rows=3)

    sentences = leaf.sentences or ([leaf.body] if leaf.body else [])
    if not sentences:
        console.print("[yellow]\uff08\u672c\u5c0f\u8282\u6682\u65e0\u6b63\u6587\u3002\u6309 Esc \u8fd4\u56de\u3002\uff09[/]")
        return _wait_for_back()

    with key_reader(with_mouse=True) as read:
        idx = 0
        _type_out_sentence(session, sentences[idx], idx, read)

        while True:
            key = read()
            if key is None:
                continue
            action = _classify(key, session)
            if action == "quit":
                session.finish_leaf()
                return "quit"
            if action == "back":
                session.finish_leaf()
                return "back"
            if action == "next":
                if idx + 1 >= len(sentences):
                    session.finish_leaf()
                    return "done"
                idx += 1
                _type_out_sentence(session, sentences[idx], idx, read)
            elif action == "prev":
                if idx == 0:
                    continue
                idx -= 1
                _type_out_sentence(session, sentences[idx], idx, read, instant=True)
            elif action == "jump_end":
                while idx + 1 < len(sentences):
                    idx += 1
                    _type_out_sentence(session, sentences[idx], idx, read, instant=True)


def _type_out_sentence(
    session: ReadingSession,
    sentence: str,
    sent_idx: int,
    read,
    *,
    instant: bool = False,
) -> None:
    """Reveal a sentence, feeding the session so spans/progress stay in sync."""
    session.begin_sentence(sent_idx, sentence)
    for ch, is_bold in iter_bionic_chars(sentence):
        session.write_char(ch, is_bold)
        if not instant:
            time.sleep(CHAR_TYPE_DELAY)
            _drain_mouse_events(read, session)
    # Separate sentences with a single newline (synthetic; not counted).
    session.write_char("\n", False, count_for_progress=False)
    session.end_sentence()


def _render_header(console: Console, leaf: Node) -> None:
    console.clear()
    console.print(f"[bold cyan]{leaf.title}[/]")
    console.print(
        "[dim]Tab \u4e0b\u4e00\u53e5  Shift+Tab \u4e0a\u4e00\u53e5  Space \u8df3\u5230\u672b\u53e5  h \u9ad8\u4eae  Esc \u8fd4\u56de  q \u9000\u51fa[/]"
    )
    console.print()


def _classify(key: Key, session: ReadingSession) -> str:
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
    if k == "h":
        session.toggle_highlight()
        return "noop"
    if k == "mouse":
        _handle_mouse(key, session)
        return "noop"
    return "noop"


def _handle_mouse(key: Key, session: ReadingSession) -> None:
    ev = parse_mouse(key.raw)
    if ev is None:
        return
    abs_row = ev.row + session.scroll_offset
    span = session.span_at(abs_row, ev.col)
    if ev.kind == "move":
        session.hover(span)
    elif ev.kind == "press" and ev.button == 0 and span is not None:
        session.toggle_highlight(span)


def _drain_mouse_events(read, session: ReadingSession) -> None:
    """Poll for queued mouse events while a char is being typed out.

    We intentionally DO NOT consume non-mouse keys here \u2014 those belong
    to the main loop so the user doesn't lose a Tab or Esc press.
    """
    while True:
        key = read(timeout=0)
        if key is None:
            return
        if key.key == "mouse":
            _handle_mouse(key, session)
            continue
        return


def _wait_for_back() -> str:
    with key_reader(with_mouse=False) as read:
        while True:
            k = read()
            if k is None:
                continue
            if k.key in ("escape", "b", "q", "ctrl-c"):
                return "back" if k.key != "q" else "quit"
